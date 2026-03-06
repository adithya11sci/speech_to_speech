import logging
import numpy as np
from faster_whisper import WhisperModel
from config import ASR_MODEL_SIZE

logger = logging.getLogger(__name__)


class ASR:
    def __init__(self, model_size: str = ASR_MODEL_SIZE, device: str = "cuda"):
        self.model_size = model_size
        self.device = device
        logger.info(f"Loading faster-whisper {model_size} on {device}...")
        try:
            self.model = WhisperModel(
                model_size,
                device=device,
                compute_type="float16" if device == "cuda" else "int8",
            )
            # Verify CUDA works by running a tiny dummy pass
            if device == "cuda":
                import numpy as np
                dummy = np.zeros(16000, dtype=np.float32)
                list(self.model.transcribe(dummy, language="en")[0])
        except Exception as e:
            if device == "cuda":
                logger.warning(f"CUDA ASR failed ({e}), falling back to CPU")
                self.device = "cpu"
                self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
            else:
                raise
        logger.info(f"ASR model loaded on {self.device}")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        segments, info = self.model.transcribe(
            audio,
            language="en",
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=200,  # less aggressive, don't cut words
                speech_pad_ms=150,            # shorter pad keeps latency low
                threshold=0.3,                # lower threshold = keep more audio
            ),
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
