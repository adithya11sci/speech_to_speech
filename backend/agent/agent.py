import os
import re
import asyncio
import logging
import threading
import json
import numpy as np
import io
import wave
from scipy import signal
from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli
from livekit.api import AccessToken, VideoGrants
from aiohttp import web

from config import (
    LIVEKIT_URL,
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LLAMA_SERVER_URL,
    KOKORO_MODEL_PATH,
    KOKORO_VOICES_PATH,
    DEFAULT_VOICE,
    SYSTEM_PROMPT,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

asr_model = None
llm_client = None
tts_model = None


def prewarm():
    global asr_model, llm_client, tts_model
    logger.info("=== Pre-warming all models ===")
    
    from asr import ASR
    asr_model = ASR()
    logger.info("ASR loaded")
    
    from llm import LLM
    llm_client = LLM(LLAMA_SERVER_URL)
    llm_client.warmup()
    logger.info("LLM warmed up")
    
    from tts import TTS
    tts_model = TTS(str(KOKORO_MODEL_PATH), str(KOKORO_VOICES_PATH), DEFAULT_VOICE)
    logger.info("TTS loaded")
    
    logger.info("=== All models ready ===")


async def entrypoint(ctx: JobContext):
    global asr_model, llm_client, tts_model

    # Models run in a subprocess — load them here if not already loaded
    if asr_model is None or llm_client is None or tts_model is None:
        logger.info("Loading models in job subprocess...")
        prewarm()

    logger.info(f"Starting voice agent for room: {ctx.room.name}")

    audio_source = rtc.AudioSource(sample_rate=48000, num_channels=1)
    track = rtc.LocalAudioTrack.create_audio_track("agent_audio", audio_source)

    conversation_history = []
    Speaking = False

    async def process_audio(audio_track):
        nonlocal Speaking, conversation_history

        audio_buffer = []
        silence_frames = 0

        # Ask AudioStream to deliver frames already at 16kHz mono — no manual resampling needed
        async for event in rtc.AudioStream(audio_track, sample_rate=16000, num_channels=1):
            pcm_data = np.frombuffer(event.frame.data, dtype=np.int16)
            float_data = pcm_data.astype(np.float32) / 32768.0
            audio_buffer.append(float_data)

            if np.abs(float_data).max() < 0.01:
                silence_frames += 1
            else:
                silence_frames = 0

            # ~1.5 seconds of audio at 16kHz (150 frames × ~160 samples each)
            if len(audio_buffer) >= 150:
                full_audio = np.concatenate(audio_buffer)
                audio_buffer = []

                try:
                    text = asr_model.transcribe(full_audio, 16000)

                    if text and len(text.strip()) > 2:
                        if not Speaking:
                            Speaking = True
                            logger.info(f"User: {text}")

                            await ctx.room.local_participant.publish_data(
                                json.dumps({"type": "user", "text": text}).encode(),
                                reliable=True,
                            )

                            conversation_history.append({"role": "user", "content": text})

                            loop = asyncio.get_running_loop()
                            response = await loop.run_in_executor(
                                None, lambda: llm_client.generate_messages(conversation_history[-6:], SYSTEM_PROMPT)
                            )

                            logger.info(f"Assistant: {response[:80]}...")
                            conversation_history.append({"role": "assistant", "content": response})

                            await ctx.room.local_participant.publish_data(
                                json.dumps({"type": "assistant", "text": response}).encode(),
                                reliable=True,
                            )

                            # Stream TTS sentence-by-sentence so first audio plays
                            # in ~150ms instead of waiting for the full response
                            sentences = split_into_sentences(response)
                            for sentence in sentences:
                                audio_data, sr = await loop.run_in_executor(
                                    None, lambda s=sentence: tts_model.generate(s)
                                )
                                resampled = resample_wav_to_48k(audio_data, sr)
                                for i in range(0, len(resampled), 1920):
                                    chunk = resampled[i:i+1920]
                                    int16_chunk = (chunk * 32767).astype(np.int16).tobytes()
                                    await audio_source.capture_frame(rtc.AudioFrame(
                                        data=int16_chunk,
                                        sample_rate=48000,
                                        num_channels=1,
                                        samples_per_channel=len(chunk),
                                    ))
                            Speaking = False

                except Exception as e:
                    logger.error(f"Error processing audio: {e}", exc_info=True)
                    Speaking = False

    def start_track(audio_track):
        asyncio.get_event_loop().create_task(process_audio(audio_track))

    # Register BEFORE connecting so we don't miss tracks from participants already in the room
    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.info(f"Subscribed to audio track from {participant.identity}")
            start_track(track)

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    await ctx.room.local_participant.publish_track(track)

    # Handle tracks from participants who were already in the room before we connected
    for participant in ctx.room.remote_participants.values():
        for publication in participant.track_publications.values():
            if publication.track and publication.track.kind == rtc.TrackKind.KIND_AUDIO:
                logger.info(f"Found existing audio track from {participant.identity}")
                start_track(publication.track)

    logger.info("Agent ready, waiting for audio...")


def split_into_sentences(text: str) -> list:
    """Split text into sentences for streaming TTS to reduce perceived latency."""
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    # Merge fragments shorter than 20 chars into the next sentence to avoid tiny clips
    merged = []
    buf = ""
    for part in parts:
        buf = (buf + " " + part).strip() if buf else part
        if len(buf) >= 20:
            merged.append(buf)
            buf = ""
    if buf:
        if merged:
            merged[-1] += " " + buf
        else:
            merged.append(buf)
    return merged or [text]


def resample_audio(audio: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate == to_rate:
        return audio
    return signal.resample_poly(audio, to_rate, from_rate)


def resample_wav_to_48k(wav_bytes: bytes, from_rate: int = 24000) -> np.ndarray:
    buffer = io.BytesIO(wav_bytes)
    with wave.open(buffer, 'rb') as wf:
        frames = wf.readframes(wf.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    
    return resample_audio(audio, from_rate, 48000)


async def _handle_token(request: web.Request) -> web.Response:
    body = await request.json()
    room_name = body.get("roomName", "voice-room")
    identity = body.get("identity", "user")
    token = (
        AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_grants(VideoGrants(room_join=True, room=room_name))
        .to_jwt()
    )
    return web.Response(
        text=json.dumps({"token": token}),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )


async def _handle_options(request: web.Request) -> web.Response:
    return web.Response(headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    })


def start_token_server(port: int = 3000):
    async def _run():
        app = web.Application()
        app.router.add_post("/get-token", _handle_token)
        app.router.add_route("OPTIONS", "/get-token", _handle_options)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Token server listening on :{port}")
        await asyncio.Event().wait()  # run forever

    def _thread():
        asyncio.run(_run())

    t = threading.Thread(target=_thread, daemon=True)
    t.start()


if __name__ == "__main__":
    start_token_server(port=3000)
    prewarm()  # load all models into GPU before accepting any connections

    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            ws_url=LIVEKIT_URL,
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        )
    )
