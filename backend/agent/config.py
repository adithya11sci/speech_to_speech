import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
MODELS_DIR = BASE_DIR / "models"

LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")

LLAMA_SERVER_URL = os.environ.get("LLAMA_SERVER_URL", "http://localhost:8080/v1")

AVAILABLE_VOICES = {
    "af_sarah": "Female, clear and professional",
    "af_bella": "Female, warm and friendly",
    "af_heart": "Female, emotional and expressive",
    "am_michael": "Male, professional and authoritative",
    "am_fen": "Male, deep and resonant",
    "bf_emma": "Female, British accent",
    "bm_george": "Male, British accent",
}

DEFAULT_VOICE = os.environ.get("DEFAULT_VOICE", "af_sarah")

KOKORO_MODEL_PATH = MODELS_DIR / "kokoro" / "kokoro-v1.0.onnx"
KOKORO_VOICES_PATH = MODELS_DIR / "kokoro" / "voices-v1.0.bin"

ASR_MODEL_SIZE = os.environ.get("ASR_MODEL_SIZE", "base")

LLAMA_MODEL_PATH = MODELS_DIR / "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
LLAMA_CONTEXT_SIZE = int(os.environ.get("LLAMA_CONTEXT_SIZE", "2048"))

SYSTEM_PROMPT = """You are a helpful AI assistant. Keep your responses concise and natural.
Respond as if you're having a real conversation. Don't be overly formal."""
