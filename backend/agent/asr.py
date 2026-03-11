import logging
import numpy as np
from faster_whisper import WhisperModel
from config import ASR_MODEL_SIZE

logger = logging.getLogger(__name__)


class ASR:
    def __init__(self, model_size: str = ASR_MODEL_SIZE, device: str = "cpu"):
        self.model_size = model_size
        self.device = device
        logger.info(f"Loading faster-whisper {model_size} on {device}...")
        try:
            self.model = WhisperModel(
                model_size,
                device=device,
                compute_type="int8",  # Use int8 for CPU
            )
        except Exception as e:
            logger.error(f"Failed to load ASR model: {e}")
            raise
        logger.info(f"ASR model loaded on {self.device}")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        segments, info = self.model.transcribe(
            audio,
            language="en",
            beam_size=5,
            vad_filter=True,  # Enable VAD to filter out silence
            vad_parameters=dict(
                threshold=0.5,  # Higher threshold for voice activity
                min_speech_duration_ms=250,  # Minimum speech duration
                min_silence_duration_ms=1000,  # Longer silence required
            ),
            initial_prompt="",  # No initial prompt
            log_prob_threshold=-1.0,  # More strict - reject low confidence
            no_speech_threshold=0.6,   # Higher threshold - reject non-speech
            compression_ratio_threshold=2.4,  # Reject highly compressed (noisy) audio
        )
        text = " ".join([seg.text for seg in segments])
        return text.strip()

    def transcribe_streaming(self, audio: np.ndarray, sample_rate: int = 16000):
        segments, info = self.model.transcribe(
            audio,
            language="en",
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        for seg in segments:
            yield seg.text
