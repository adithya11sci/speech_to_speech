"""
LiveKit Voice Agent for Real-time AI Conversations

This agent connects to a LiveKit room and provides real-time voice interactions:
1. Listens to participant audio streams
2. Transcribes speech using Faster Whisper (ASR)
3. Generates responses using Groq LLM
4. Synthesizes speech using Kokoro TTS
5. Streams audio back to the room

Features:
- Concurrent processing prevention with async locks
- Sentence-by-sentence TTS streaming for low latency
- Automatic track discovery and management
- CORS-enabled token server for frontend authentication
"""

from __future__ import annotations
import sys
from pathlib import Path

# Add backend/agent/ to path so config, asr, llm, tts modules resolve
sys.path.insert(0, str(Path(__file__).parent / "agent"))

import os
import re
import asyncio
import logging
import threading
import json
import numpy as np
import io
import wave
from typing import TYPE_CHECKING
from scipy import signal
from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli
from livekit.api import AccessToken, VideoGrants
from aiohttp import web

if TYPE_CHECKING:
    from asr import ASR
    from llm import LLM
    from tts import TTS

from config import (
    LIVEKIT_URL,
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    GROQ_API_KEY,
    GROQ_API_BASE,
    GROQ_MODEL,
    KOKORO_MODEL_PATH,
    KOKORO_VOICES_PATH,
    DEFAULT_VOICE,
    SYSTEM_PROMPT,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global model instances (loaded during prewarm)
asr_model: ASR | None = None
llm_client: LLM | None = None
tts_model: TTS | None = None


def prewarm():
    """
    Pre-load all AI models (ASR, LLM, TTS) into memory before accepting connections.
    This ensures the first user interaction has minimal latency.
    
    Models are loaded as global singletons and reused across all sessions.
    """
    global asr_model, llm_client, tts_model
    logger.info("=== Pre-warming all models ===")

    from asr import ASR
    asr_model = ASR()
    logger.info("✅ ASR (Faster Whisper) loaded")

    from llm import LLM
    llm_client = LLM(GROQ_API_BASE, GROQ_API_KEY, GROQ_MODEL)
    llm_client.warmup()
    logger.info("✅ LLM (Groq) client ready")

    from tts import TTS
    tts_model = TTS(str(KOKORO_MODEL_PATH), str(KOKORO_VOICES_PATH), DEFAULT_VOICE)
    logger.info("✅ TTS (Kokoro) loaded")

    logger.info("=== All models ready ===")



async def entrypoint(ctx: JobContext):
    global asr_model, llm_client, tts_model

    # Models run in a subprocess — load them here if not already loaded
    if asr_model is None or llm_client is None or tts_model is None:
        logger.info("Loading models in job subprocess...")
        prewarm()
    
    # Type guard: Ensure models are loaded
    if asr_model is None or llm_client is None or tts_model is None:
        raise RuntimeError("Failed to load models. Check logs for errors.")

    logger.info(f"Starting voice agent for room: {ctx.room.name}")

    audio_source = rtc.AudioSource(sample_rate=48000, num_channels=1)
    track = rtc.LocalAudioTrack.create_audio_track("agent_audio", audio_source)

    conversation_history = []
    processing_lock = asyncio.Lock()  # Prevent concurrent processing
    active_tasks = set()  # Track active audio processing tasks
    processed_tracks = set()  # Prevent duplicate track processing

    async def process_audio(audio_track, participant_id):
        """Process audio from a single participant's track."""
        # Type narrowing: models are guaranteed to be loaded by this point
        assert asr_model is not None, "ASR model not loaded"
        assert llm_client is not None, "LLM client not loaded"
        assert tts_model is not None, "TTS model not loaded"
        
        # Capture models with proper types for lambda closures
        _asr = asr_model
        _llm = llm_client
        _tts = tts_model
        
        track_id = f"{participant_id}_{id(audio_track)}"
        
        if track_id in processed_tracks:
            logger.warning(f"Track {track_id} already being processed, skipping")
            return
        
        processed_tracks.add(track_id)
        logger.info(f"Starting audio processing for track {track_id}")
        
        audio_buffer = []
        silence_frames = 0
        last_speech_time = 0

        try:
            # Ask AudioStream to deliver frames already at 16kHz mono
            async for event in rtc.AudioStream(audio_track, sample_rate=16000, num_channels=1):
                pcm_data = np.frombuffer(event.frame.data, dtype=np.int16)
                float_data = pcm_data.astype(np.float32) / 32768.0
                audio_buffer.append(float_data)

                # Detect voice activity
                volume = np.abs(float_data).max()
                if volume > 0.01:  # Voice detected
                    silence_frames = 0
                    last_speech_time = len(audio_buffer)
                else:
                    silence_frames += 1

                # Process when we have enough audio with silence after speech
                buffer_length = len(audio_buffer)
                should_process = (
                    (buffer_length >= 400) or  # ~4 seconds of audio
                    (buffer_length >= 100 and silence_frames > 100 and last_speech_time > 0)  # 1s silence after speech
                )
                
                if should_process and audio_buffer:
                    # Check if we can process (not already processing)
                    if processing_lock.locked():
                        logger.debug("Already processing speech, skipping this buffer")
                        audio_buffer = []
                        silence_frames = 0
                        last_speech_time = 0
                        continue
                    
                    async with processing_lock:
                        full_audio = np.concatenate(audio_buffer)
                        audio_buffer = []
                        silence_frames = 0
                        last_speech_time = 0

                        try:
                            # Transcribe audio
                            loop = asyncio.get_running_loop()
                            text = await loop.run_in_executor(
                                None, lambda: _asr.transcribe(full_audio, 16000)
                            )
                            
                            logger.info(f"📝 Transcription: '{text}' (length: {len(text.strip())})")

                            # Only process if we have meaningful text
                            if text and len(text.strip()) > 2:
                                logger.info(f"👤 User: {text}")

                                # Publish user message
                                await ctx.room.local_participant.publish_data(
                                    json.dumps({"type": "user", "text": text}).encode(),
                                    reliable=True,
                                )

                                # Add to conversation history
                                conversation_history.append({"role": "user", "content": text})

                                # Generate LLM response
                                response = await loop.run_in_executor(
                                    None, 
                                    lambda: _llm.generate_messages(
                                        conversation_history[-6:], 
                                        SYSTEM_PROMPT
                                    )
                                )

                                logger.info(f"🤖 Assistant: {response[:80]}...")
                                conversation_history.append({"role": "assistant", "content": response})

                                # Publish assistant message
                                await ctx.room.local_participant.publish_data(
                                    json.dumps({"type": "assistant", "text": response}).encode(),
                                    reliable=True,
                                )

                                # Stream TTS sentence-by-sentence for lower latency
                                sentences = split_into_sentences(response)
                                for sentence in sentences:
                                    audio_data, sr = await loop.run_in_executor(
                                        None, lambda s=sentence: _tts.generate(s)
                                    )
                                    resampled = resample_wav_to_48k(audio_data, sr)
                                    
                                    # Send audio in chunks
                                    for i in range(0, len(resampled), 1920):
                                        chunk = resampled[i:i+1920]
                                        if len(chunk) > 0:
                                            int16_chunk = (chunk * 32767).astype(np.int16).tobytes()
                                            await audio_source.capture_frame(rtc.AudioFrame(
                                                data=int16_chunk,
                                                sample_rate=48000,
                                                num_channels=1,
                                                samples_per_channel=len(chunk),
                                            ))
                            else:
                                logger.debug(f"Ignoring short/empty transcription: '{text}'")

                        except Exception as e:
                            logger.error(f"Error processing speech: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error in audio stream for {track_id}: {e}", exc_info=True)
        finally:
            processed_tracks.discard(track_id)
            logger.info(f"Stopped processing track {track_id}")

    def start_track(audio_track, participant_id):
        """Start processing an audio track in a managed task."""
        task = asyncio.create_task(process_audio(audio_track, participant_id))
        active_tasks.add(task)
        task.add_done_callback(active_tasks.discard)

    # Register event handler BEFORE connecting
    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.info(f"✅ Subscribed to audio track from {participant.identity}")
            start_track(track, participant.identity)

    # Connect to the room
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    await ctx.room.local_participant.publish_track(track)

    # Handle existing participants already in the room
    for participant in ctx.room.remote_participants.values():
        for publication in participant.track_publications.values():
            if publication.track and publication.track.kind == rtc.TrackKind.KIND_AUDIO:
                logger.info(f"✅ Found existing audio track from {participant.identity}")
                start_track(publication.track, participant.identity)

    logger.info("🎤 Agent ready and listening for audio...")


def split_into_sentences(text: str) -> list:
    """
    Split text into sentences for streaming TTS to reduce perceived latency.
    Merges fragments shorter than 20 characters to avoid tiny audio clips.
    """
    if not text or not text.strip():
        return []
    
    # Split on sentence-ending punctuation followed by whitespace
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    
    # Merge small fragments to avoid very short audio clips
    merged = []
    buf = ""
    for part in parts:
        buf = (buf + " " + part).strip() if buf else part
        if len(buf) >= 20:
            merged.append(buf)
            buf = ""
    
    # Append remaining buffer
    if buf:
        if merged:
            merged[-1] += " " + buf
        else:
            merged.append(buf)
    
    return merged if merged else [text]


def resample_audio(audio: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    """
    Resample audio from one sample rate to another using scipy's polyphase resampling.
    
    Args:
        audio: Input audio array
        from_rate: Source sample rate
        to_rate: Target sample rate
    
    Returns:
        Resampled audio array
    """
    if from_rate == to_rate:
        return audio
    return signal.resample_poly(audio, to_rate, from_rate)


def resample_wav_to_48k(wav_bytes: bytes, from_rate: int = 24000) -> np.ndarray:
    """
    Convert WAV bytes to 48kHz float32 audio for LiveKit.
    
    Args:
        wav_bytes: WAV file as bytes
        from_rate: Source sample rate (default 24000 for Kokoro TTS)
    
    Returns:
        Float32 audio array at 48kHz
    """
    try:
        buffer = io.BytesIO(wav_bytes)
        with wave.open(buffer, 'rb') as wf:
            frames = wf.readframes(wf.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

        return resample_audio(audio, from_rate, 48000)
    except Exception as e:
        logger.error(f"Error resampling WAV: {e}")
        raise


async def _handle_token(request: web.Request) -> web.Response:
    """Handle token generation requests for LiveKit room access."""
    try:
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
    except Exception as e:
        logger.error(f"Error generating token: {e}")
        return web.Response(
            text=json.dumps({"error": "Failed to generate token"}),
            content_type="application/json",
            status=500,
            headers={"Access-Control-Allow-Origin": "*"},
        )


async def _handle_options(request: web.Request) -> web.Response:
    """Handle CORS preflight requests."""
    return web.Response(headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    })


def start_token_server(port: int = 3000):
    """
    Start HTTP server for generating LiveKit access tokens.
    Runs in a background thread to not block the main agent loop.
    
    Args:
        port: Port to listen on (default 3000)
    """
    async def _run():
        app = web.Application()
        app.router.add_post("/get-token", _handle_token)
        app.router.add_route("OPTIONS", "/get-token", _handle_options)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"🔑 Token server listening on http://0.0.0.0:{port}")
        await asyncio.Event().wait()  # run forever

    def _thread():
        try:
            asyncio.run(_run())
        except Exception as e:
            logger.error(f"Token server error: {e}", exc_info=True)

    t = threading.Thread(target=_thread, daemon=True)
    t.start()


if __name__ == "__main__":
    # Start background token server for frontend authentication
    start_token_server(port=3000)
    
    # Pre-load all models before accepting any connections
    # This ensures minimal latency for the first user interaction
    prewarm()

    # Start the LiveKit agent worker
    logger.info("🚀 Starting LiveKit agent worker...")
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            ws_url=LIVEKIT_URL,
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        )
    )
