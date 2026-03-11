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
            vad_filter=False,  # Disable VAD - causing issues
            initial_prompt="",  # No initial prompt
            log_prob_threshold=-2.5,  # Very lenient
            no_speech_threshold=0.9,   # Very lenient
            compression_ratio_threshold=4.0,  # Very lenient
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
