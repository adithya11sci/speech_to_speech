import logging
import numpy as np
import io
import wave
from kokoro_onnx import Kokoro

logger = logging.getLogger(__name__)


def _patched_create_audio(self, phonemes, voice, speed):
    """Patch for kokoro-onnx 0.5.0 bug: speed dtype is int32 instead of float32
    in the newer ONNX export branch (input_ids model)."""
    MAX_PHONEME_LENGTH = 510
    SAMPLE_RATE = 24000
    phonemes = phonemes[:MAX_PHONEME_LENGTH]
    tokens = np.array(self.tokenizer.tokenize(phonemes), dtype=np.int64)
    voice_slice = voice[len(tokens)]
    tokens_padded = [[0, *tokens, 0]]
    if "input_ids" in [i.name for i in self.sess.get_inputs()]:
        inputs = {
            "input_ids": tokens_padded,
            "style": np.array(voice_slice, dtype=np.float32),
            "speed": np.array([speed], dtype=np.float32),  # fix: was int32
        }
    else:
        inputs = {
            "tokens": tokens_padded,
            "style": voice_slice,
            "speed": np.ones(1, dtype=np.float32) * speed,
        }
    audio = self.sess.run(None, inputs)[0]
    return audio, SAMPLE_RATE


class TTS:
    def __init__(self, model_path: str, voices_path: str, voice: str = "af_sarah"):
        logger.info(f"Loading Kokoro TTS with voice {voice}...")
        self.kokoro = Kokoro(model_path, voices_path)
        # Patch kokoro-onnx 0.5.0 bug: speed passed as int32 instead of float32
        import types
        self.kokoro._create_audio = types.MethodType(_patched_create_audio, self.kokoro)
        self.voice = voice
        self.sample_rate = 24000
        logger.info("TTS model loaded")

    def set_voice(self, voice: str):
        self.voice = voice

    def generate(self, text: str) -> tuple[bytes, int]:
        samples, sample_rate = self.kokoro.create(
            text,
            voice=self.voice,
            speed=1.0,
        )
        audio = (samples * 32767).astype(np.int16)
        
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio.tobytes())
        
        return buffer.getvalue(), sample_rate

    def generate_raw(self, text: str) -> np.ndarray:
        samples, _ = self.kokoro.create(
            text,
            voice=self.voice,
            speed=1.0,
        )
        audio = (samples * 32767).astype(np.int16)
        return audio

    def text_to_audio_streaming(self, text: str):
        samples, _ = self.kokoro.create(
            text,
            voice=self.voice,
            speed=1.0,
        )
        audio = (samples * 32767).astype(np.int16)
        yield audio.tobytes()
