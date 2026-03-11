import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(Path(__file__).parent.parent / ".env")

BASE_DIR = Path(__file__).parent.parent
MODELS_DIR = BASE_DIR / "models"

# LiveKit Configuration
LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")

# Groq API Configuration
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")  # Set in .env file
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in environment variables. Please set it in backend/.env")
GROQ_API_BASE = "https://api.groq.com/openai/v1"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

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

SYSTEM_PROMPT = """You are a helpful AI assistant. Keep your responses concise and natural.
Respond as if you're having a real conversation. Don't be overly formal."""
