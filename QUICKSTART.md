# 🚀 Quick Start Guide

## One-Command Setup (Recommended)

```powershell
.\setup_all.ps1
```

This will:
- Download and configure LiveKit server (no Docker!)
- Install Python dependencies
- Install Node.js dependencies

## Running the Application

You need **3 terminals**:

### Terminal 1: LiveKit Server
```powershell
.\start_livekit.ps1
```

### Terminal 2: Backend
```powershell
.\start_backend.ps1
```

### Terminal 3: Frontend
```powershell
.\start_frontend.ps1
```

Then open **http://localhost:5173** in your browser!

## What You Get

- 🎤 **Real-time voice conversation** with AI
- 🤖 **Groq API** for ultra-fast LLM responses
- 🔊 **Kokoro TTS** for natural voice output
- ⚡ **~200ms latency** end-to-end

## Troubleshooting

### "Cannot run script" error
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### LiveKit server won't start
Make sure port 7880 is not in use:
```powershell
netstat -ano | findstr :7880
```

### Python dependencies fail
Make sure you have Python 3.8+ installed:
```powershell
python --version
```

## Configuration

Edit `backend\.env` to change:
- `GROQ_API_KEY` - Your Groq API key
- `GROQ_MODEL` - AI model (default: llama-3.1-8b-instant)
- `DEFAULT_VOICE` - TTS voice (af_sarah, af_bella, am_michael, etc.)
- `ASR_MODEL_SIZE` - Speech recognition model (tiny, base, small)

## See README.md for full documentation
