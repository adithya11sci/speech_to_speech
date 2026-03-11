# 🎤 Voice AI Assistant - Complete Workflow

## 📋 System Overview

**What it does:** Takes your voice input → processes with AI → responds with voice

```
┌─────────────────────────────────────────────────────────────────────┐
│                        VOICE TO VOICE WORKFLOW                       │
└─────────────────────────────────────────────────────────────────────┘

   YOU SPEAK                                              AI SPEAKS BACK
      ↓                                                          ↑
┌──────────────┐      ┌──────────────┐      ┌──────────────────────────┐
│   Browser    │      │   LiveKit    │      │    Backend Agent         │
│  (Frontend)  │ ←──→ │    Server    │ ←──→ │                          │
│              │      │   (WebRTC)   │      │  ┌────────────────────┐  │
│ • Microphone │      │              │      │  │ 1. ASR (Whisper)   │  │
│ • Speaker    │      │ • Audio      │      │  │    Voice → Text    │  │
│ • UI         │      │   Streaming  │      │  └────────────────────┘  │
└──────────────┘      │ • Real-time  │      │           ↓              │
                      │   Transport  │      │  ┌────────────────────┐  │
                      └──────────────┘      │  │ 2. LLM (Groq API)  │  │
                                            │  │    Text → Response │  │
                                            │  └────────────────────┘  │
                                            │           ↓              │
                                            │  ┌────────────────────┐  │
                                            │  │ 3. TTS (Kokoro)    │  │
                                            │  │    Text → Voice    │  │
                                            │  └────────────────────┘  │
                                            └──────────────────────────┘
```

---

## 🔄 Step-by-Step Flow

### **Step 1: User Speaks** 🎤
- You speak into your computer's microphone
- Browser captures audio in real-time
- Audio is sent via WebRTC to LiveKit server

### **Step 2: Audio Transport** 🌐
- LiveKit server routes audio to Backend Agent
- Uses WebRTC protocol for low-latency streaming
- Real-time connection maintained

### **Step 3: Speech-to-Text (ASR)** 📝
- **Tool**: faster-whisper (base model)
- **Process**: Converts your voice to text
- **Time**: ~500ms-1s
- **Example**: "Hello, how are you?" → text

### **Step 4: AI Processing (LLM)** 🤖
- **API**: Groq (llama-3.1-8b-instant)
- **API Key**: Set in backend/.env file
- **Process**: Generates intelligent response
- **Time**: ~200-500ms (ultra-fast cloud inference)
- **Example**: 
  - Input: "Hello, how are you?"
  - Output: "I'm doing great! How can I help you today?"

### **Step 5: Text-to-Speech (TTS)** 🔊
- **Tool**: Kokoro ONNX (af_sarah voice)
- **Process**: Converts AI response text to natural voice
- **Time**: ~300-500ms
- **Output**: Audio stream

### **Step 6: Voice Playback** 🔉
- Audio sent back through LiveKit
- Your browser plays the AI's voice response
- You hear the AI speaking naturally

---

## ⚡ Complete Latency

| Stage | Time | Component |
|-------|------|-----------|
| Voice capture | ~100ms | Browser microphone |
| Audio transport | ~50ms | WebRTC/LiveKit |
| Speech-to-Text | ~500ms | faster-whisper |
| AI processing | ~300ms | **Groq API** (cloud) |
| Text-to-Speech | ~400ms | Kokoro TTS |
| Audio playback | ~50ms | WebRTC/LiveKit |
| **TOTAL** | **~1.4s** | End-to-end |

---

## 🎯 Your Configuration

### Voice Input ✅
- **Microphone**: System default microphone
- **Sample Rate**: 16kHz
- **Format**: PCM audio stream

### AI Processing ✅
- **Provider**: Groq Cloud API
- **Model**: llama-3.1-8b-instant
- **API Key**: Configured in `.env`
- **Response Type**: Conversational text

### Voice Output ✅  
- **TTS Engine**: Kokoro ONNX
- **Voice**: af_sarah (Female, clear)
- **Sample Rate**: 24kHz → 48kHz
- **Format**: Real-time audio stream

---

## 🔧 Current Setup Status

### Running Services:
1. ✅ **LiveKit Server** - Port 7880 (Audio transport)
2. ✅ **Backend Agent** - Python process (AI processing)
3. ✅ **Frontend** - http://localhost:5173 (User interface)

### Configured APIs:
- ✅ **Groq API** - For AI text generation
- ✅ **Local TTS** - Kokoro for voice synthesis
- ✅ **Local ASR** - faster-whisper for speech recognition

---

## 📱 How to Use

1. **Open**: http://localhost:5173
2. **Click**: "Connect" button
3. **Allow**: Microphone permission
4. **Speak**: Talk normally (2-3 seconds)
5. **Listen**: AI responds with voice
6. **Continue**: Have a conversation!

---

## 🎨 Available Voices

You can change the voice in `backend/.env`:

```bash
DEFAULT_VOICE=af_sarah    # Female, clear (current)
# DEFAULT_VOICE=af_bella  # Female, warm
# DEFAULT_VOICE=af_heart  # Female, emotional  
# DEFAULT_VOICE=am_michael # Male, professional
# DEFAULT_VOICE=am_fen    # Male, deep
```

---

## 🔍 Troubleshooting

### No Voice Recognition?
- Speak louder and clearer
- Check microphone permissions in browser
- Wait 2-3 seconds after speaking

### No Voice Response?
- Check backend terminal for errors
- Verify Groq API key is valid
- Ensure all 3 services are running

### Poor Quality?
- Use a better microphone
- Reduce background noise
- Speak at normal pace

---

## 💡 Architecture Benefits

✅ **Low Latency**: ~1.4s end-to-end response
✅ **Cloud LLM**: Ultra-fast Groq API (no local model needed)
✅ **Local TTS/ASR**: Privacy-friendly, no external voice APIs
✅ **Real-time**: WebRTC for instant audio streaming
✅ **Scalable**: Can handle multiple conversations

---

## 📊 Data Flow Diagram

```
Browser Microphone
        ↓
   [Audio Capture]
        ↓
   [WebRTC Send] → LiveKit Server → [WebRTC Receive]
                                            ↓
                                    Backend Agent
                                            ↓
                               [Buffer 2.5s Audio]
                                            ↓
                              [ASR: faster-whisper]
                                            ↓
                                   [Text: "Hello"]
                                            ↓
                              [LLM: Groq API Call]
                    HTTP → api.groq.com/openai/v1 → HTTP
                                            ↓
                        [Text: "Hi! How can I help?"]
                                            ↓
                              [TTS: Kokoro ONNX]
                                            ↓
                                    [Audio Stream]
                                            ↓
   [WebRTC Receive] ← LiveKit Server ← [WebRTC Send]
        ↓
   [Audio Playback]
        ↓
  Browser Speaker
```

---

## ✨ Summary

**INPUT**: Your voice → Microphone → Browser
**PROCESS**: ASR → Groq API → TTS  
**OUTPUT**: AI voice → Browser → Speaker

**Result**: Natural voice-to-voice AI conversation! 🎉
