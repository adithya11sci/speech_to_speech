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
| **LLM** | Llama-3.2-3B-Instruct-Q4_K_M.gguf | Via llama-server |
| **TTS** | kokoro-onnx | Multiple voices available |

### Latency Budget

| Stage | Target | Notes |
|-------|--------|-------|
| Audio capture → ASR | 40-60ms | Use `tiny` model |
| ASR → LLM (first token) | 80-120ms | Pre-warm, short prompts |
| LLM streaming | 20-30ms/token | Q4 quantization |
| LLM → TTS first audio | 40-60ms | GPU inference |
| WebRTC transport | 20-40ms | Local network |
| **Total** | **~200-310ms** | With optimizations |

### Key Optimizations

1. **Pre-warm on startup** - Load all models before accepting connections
2. **Use llama-server** - Better streaming than llama-cpp-python
3. **Async pipeline** - Stream TTS while LLM generates
4. **Minimal prompt length** - Faster TTFT
5. **Continuous context** - Keep LLM warm between interactions

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
│   ├── models/
│   │   ├── kokoro/
│   │   │   ├── kokoro-v1.0.onnx
│   │   │   └── voices-v1.0.bin
│   │   └── Llama-3.2-3B-Instruct-Q4_K_M.gguf
│   ├── agent/
│   │   ├── agent.py          # LiveKit agent
│   │   ├── asr.py           # faster-whisper wrapper
│   │   ├── llm.py           # llama-server client
│   │   ├── tts.py           # kokoro-onnx wrapper
│   │   └── config.py        # Avatar configs
│   ├── frontend/
│   │   └── index.html       # WebRTC client
│   └── server.py            # Backend server
├── README.md
└── PHASES.md
```

---

## Running the Project

### Prerequisites

1. Install Docker
2. Install llama-server: `llama-server` in PATH

### Quick Start

```bash
# 1. Start LiveKit server
docker run --rm -d --name livekit-server -p 7880:7880 -p 7881:7881 -p 7882:7882/udp livekit/livekit-server:latest --dev --bind 0.0.0.0 --node-ip 127.0.0.1

# 2. Start llama-server (separate terminal)
llama-server -m ./backend/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf -c 2048 -ngl 32 --port 8080

# 3. Start agent
cd backend/agent
pip install -r requirements.txt
python agent.py

# 4. Open frontend
# Visit http://localhost:3000
```

### Environment Variables

```bash
# .env
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret
LLAMA_SERVER_URL=http://localhost:8080/v1
DEFAULT_VOICE=af_sarah
```

---

## Credits

- **LiveKit** - WebRTC infrastructure
- **faster-whisper** - Fast ASR
- **llama.cpp** - Local LLM inference
- **kokoro-onnx** - Fast TTS
- **MuseTalk** - Lip-sync (Phase 2)
