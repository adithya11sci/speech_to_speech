# Avatar Gen - Real-Time Voice Avatar Project

## Overview

A low-latency voice avatar system that processes speech in real-time using ASR → LLM → TTS pipeline, with optional lip-sync avatar animation (Phase 2).

**Target Latency**: ~300ms end-to-end for Phase 1

---

## Architecture

```
┌─────────────┐    ┌────────────────────────────────────────┐    ┌─────────────┐
│   Browser   │◄──►│         LiveKit Agent (Python)          │◄──►│   MuseTalk  │
│  (WebRTC)   │    │  faster-whisper → LLM → kokoro-onnx   │    │  (Phase 2) │
└─────────────┘    └────────────────────────────────────────┘    └─────────────┘
```

---

## Hardware

- **GPU**: NVIDIA RTX 4060 Laptop (8GB VRAM)
- **RAM**: 16GB+ recommended

---

## Phase 1: ASR → LLM → TTS (Current)

### Components

| Component | Model | Notes |
|-----------|-------|-------|
| **ASR** | faster-whisper (`tiny` or `base`) | 4x faster than vanilla Whisper |
| **LLM** | Groq API (llama-3.1-8b-instant) | Cloud-based, ultra-fast inference |
| **TTS** | kokoro-onnx | Multiple voices available |

### Latency Budget

| Stage | Target | Notes |
|-------|--------|-------|
| Audio capture → ASR | 40-60ms | Use `base` model |
| ASR → LLM (first token) | 50-100ms | Groq ultra-fast inference |
| LLM streaming | 10-20ms/token | Cloud-based |
| LLM → TTS first audio | 40-60ms | GPU inference |
| WebRTC transport | 20-40ms | Local network |
| **Total** | **~160-280ms** | With optimizations |

### Key Optimizations

1. **Pre-warm on startup** - Load all models before accepting connections
2. **Use Groq API** - Ultra-fast cloud-based LLM inference
3. **Async pipeline** - Stream TTS while LLM generates
4. **Minimal prompt length** - Faster TTFT
5. **Continuous context** - Maintain conversation history

### Voice Options (Kokoro)

Configure voice in avatar config:

```json
{
  "voice": "af_sarah"
}
```

Available voices:
- `af_sarah` - Female, clear
- `af_bella` - Female, warm
- `af_heart` - Female, emotional
- `am_michael` - Male, professional
- `am_fen` - Male, deep

---

## Phase 2: MuseTalk Integration (Future)

### What's Added

- Lip-sync avatar animation using MuseTalk
- Video streaming via LiveKit
- AV sync coordination

### MuseTalk Requirements

1. **Avatar Preparation** - Pre-process video source to extract:
   - Latents (VAE encoded)
   - Face coordinates
   - Masks

2. **Inference** - For each audio chunk:
   - Extract Whisper features
   - Generate face frames via UNet
   - Blend with original avatar

### Integration Points

- TTS audio goes to both: browser + MuseTalk
- MuseTalk outputs video frames
- LiveKit streams video track to browser
- Frame-level sync via audio timestamps

---

## Project Structure

```
Avatar_gen/
├── backend/
│   ├── agent.py              # LiveKit agent + token server (entry point)
│   ├── agent/
│   │   ├── asr.py            # faster-whisper wrapper
│   │   ├── llm.py            # Groq API client
│   │   ├── tts.py            # kokoro-onnx wrapper
│   │   ├── config.py         # all configuration
│   │   └── requirements.txt
│   ├── models/
│   │   └── kokoro/
│   │       ├── kokoro-v1.0.onnx
│   │       └── voices-v1.0.bin
│   └── .env
├── frontend/
│   └── src/
│       ├── App.tsx
│       └── index.css
├── README.md
└── phase_2.md
```

---

## Running the Project

### Prerequisites

1. **Python 3.8+** - With pip
2. **Node.js 16+** - With npm
3. **Groq API Key** - Already configured in `.env`
4. **No Docker needed!** - We'll use LiveKit native binary

### Quick Start

#### Step 1: Setup LiveKit Server (One-time)

```powershell
# Run from project root
.\setup_livekit.ps1
```

This will download and configure LiveKit server (~15MB).

#### Step 2: Start LiveKit Server (Keep running)

```powershell
# Terminal 1 - Start LiveKit server
.\start_livekit.ps1
```

Wait until you see "Starting LiveKit server" message.

#### Step 3: Start Backend Agent (Keep running)

```powershell
# Terminal 2 - Start backend
.\start_backend.ps1
```

Wait for "All models ready" message.

#### Step 4: Start Frontend

```powershell
# Terminal 3 - Start frontend
.\start_frontend.ps1
```

Then visit **http://localhost:5173** in your browser!

### Manual Setup (If scripts don't work)

```powershell
# 1. Download LiveKit server from:
# https://github.com/livekit/livekit/releases/download/v1.8.7/livekit_v1.8.7_windows_amd64.zip
# Extract to livekit-server/ folder

# 2. Create livekit-server/config.yaml with:
# port: 7880
# keys:
#   devkey: secret

# 3. Start LiveKit (Terminal 1)
cd livekit-server
.\livekit-server.exe --config config.yaml --dev

# 4. Start Backend (Terminal 2)
cd backend
pip install -r agent/requirements.txt
python agent.py dev

# 5. Start Frontend (Terminal 3)
cd frontend
npm install
npm run dev
```

### Environment Variables

The `.env` file in `backend/` contains:

```bash
# LiveKit Configuration
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret

# Groq API Configuration
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.1-8b-instant

# Voice Configuration
DEFAULT_VOICE=af_sarah
ASR_MODEL_SIZE=base
```

---

## Credits

- **LiveKit** - WebRTC infrastructure
- **faster-whisper** - Fast ASR
- **Groq** - Ultra-fast cloud LLM inference
- **kokoro-onnx** - Fast TTS
- **MuseTalk** - Lip-sync (Phase 2)
