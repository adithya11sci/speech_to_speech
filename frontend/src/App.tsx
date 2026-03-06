import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Room,
  RoomEvent,
  Track,
  createLocalAudioTrack,
  type LocalAudioTrack,
  type RemoteTrack,
} from 'livekit-client'

const LIVEKIT_URL = 'ws://localhost:7880'

type ConnState = 'disconnected' | 'connecting' | 'connected' | 'error'

interface Message {
  id: number
  role: 'user' | 'assistant' | 'system'
  text: string
  time: string
}

let msgId = 0
const now = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

export default function App() {
  const [connState, setConnState] = useState<ConnState>('disconnected')
  const [messages, setMessages] = useState<Message[]>([
    {
      id: msgId++,
      role: 'assistant',
      text: "👋 Hello! I'm your AI voice assistant. Click <strong>Connect</strong> below, then speak — I'll reply with voice and show the conversation here.",
      time: now(),
    },
  ])
  const [msgCount, setMsgCount] = useState(0)
  const [latency, setLatency] = useState('—')
  const [isSpeaking, setIsSpeaking] = useState(false)

  const roomRef = useRef<Room | null>(null)
  const audioTrackRef = useRef<LocalAudioTrack | null>(null)
  const latencyStart = useRef<number>(0)
  const chatEndRef = useRef<HTMLDivElement>(null)

  const addMessage = useCallback((role: Message['role'], text: string) => {
    setMessages(prev => [...prev, { id: msgId++, role, text, time: now() }])
    setMsgCount(c => c + 1)
    setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
  }, [])

  const connect = useCallback(async () => {
    setConnState('connecting')
    try {
      const res = await fetch('/get-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ roomName: 'voice-room', identity: `user-${Date.now()}` }),
      })
      if (!res.ok) throw new Error('Failed to get token')
      const { token } = await res.json()

      const room = new Room({ adaptiveStream: true, dynacast: true })
      roomRef.current = room

      room.on(RoomEvent.Connected, async () => {
        setConnState('connected')
        addMessage('system', '✅ Connected. Start speaking!')
        const audioTrack = await createLocalAudioTrack({ echoCancellation: true, noiseSuppression: true })
        audioTrackRef.current = audioTrack
        await room.localParticipant.publishTrack(audioTrack)
      })

      room.on(RoomEvent.Disconnected, () => {
        setConnState('disconnected')
        addMessage('system', '🔌 Disconnected.')
        audioTrackRef.current = null
        roomRef.current = null
        setIsSpeaking(false)
      })

      room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
        if (track.kind === Track.Kind.Audio) {
          const el = track.attach()
          el.autoplay = true
          document.body.appendChild(el)
          setIsSpeaking(true)
        }
      })

      room.on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
        track.detach().forEach(el => el.remove())
        setIsSpeaking(false)
      })

      room.on(RoomEvent.DataReceived, (payload: Uint8Array) => {
        try {
          const msg = JSON.parse(new TextDecoder().decode(payload))
          if (msg.type === 'user') {
            latencyStart.current = performance.now()
            addMessage('user', msg.text)
          } else if (msg.type === 'assistant') {
            const ms = performance.now() - latencyStart.current
            setLatency(Math.round(ms) + 'ms')
            addMessage('assistant', msg.text)
            setIsSpeaking(true)
            setTimeout(() => setIsSpeaking(false), 3000)
          }
        } catch { /* ignore */ }
      })

      await room.connect(LIVEKIT_URL, token)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      addMessage('system', `⚠️ Error: ${msg}`)
      setConnState('error')
    }
  }, [addMessage])

  const disconnect = useCallback(async () => {
    audioTrackRef.current?.stop()
    audioTrackRef.current = null
    await roomRef.current?.disconnect()
    roomRef.current = null
  }, [])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView()
  }, [])

  const statusLabel =
    connState === 'connected' ? 'Live' :
    connState === 'connecting' ? 'Connecting…' :
    connState === 'error' ? 'Error' : 'Offline'

  return (
    <div className="app-container">
      <div className="bg-particles" />

      <header className="app-header">
        <div className="header-left">
          <div className="logo-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a5 5 0 0 1 5 5v3a5 5 0 0 1-10 0V7a5 5 0 0 1 5-5Z" />
              <path d="M17 10v1a5 5 0 0 1-10 0v-1" />
              <line x1="12" y1="19" x2="12" y2="22" />
              <line x1="8" y1="22" x2="16" y2="22" />
            </svg>
          </div>
          <div className="header-text">
            <h1>Avatar Gen</h1>
            <span className="subtitle">Whisper · Llama 3.2 · Kokoro TTS</span>
          </div>
        </div>
        <div className="header-right">
          <div className={`status-badge status-${connState}`}>
            <span className="status-dot" />
            <span className="status-text">{statusLabel}</span>
          </div>
          <button className="btn-icon" title="Clear chat" onClick={() => {
            setMessages([{ id: msgId++, role: 'assistant', text: '👋 Chat cleared! Ready for a new conversation.', time: now() }])
            setMsgCount(0)
            setLatency('—')
          }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            </svg>
          </button>
        </div>
      </header>

      <main className="main-content">
        {/* Left: Avatar panel */}
        <div className="avatar-panel">
          <div className="avatar-container">
            <div className="avatar-glow" />
            <div className="avatar-icon">
              <svg width="72" height="72" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
                <path d="M12 2a5 5 0 0 1 5 5v3a5 5 0 0 1-10 0V7a5 5 0 0 1 5-5Z" />
                <path d="M17 10v1a5 5 0 0 1-10 0v-1" />
                <line x1="12" y1="19" x2="12" y2="22" />
                <line x1="8" y1="22" x2="16" y2="22" />
              </svg>
            </div>
            <div className="avatar-name">AI Assistant</div>
            {isSpeaking && (
              <div className="speaking-indicator">
                {[0,1,2,3,4].map(i => (
                  <div key={i} className="wave-bar" style={{ animationDelay: `${i * 0.12}s` }} />
                ))}
              </div>
            )}
          </div>

          <div className="avatar-stats">
            <div className="stat-item">
              <span className="stat-value">{msgCount}</span>
              <span className="stat-label">Messages</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{latency}</span>
              <span className="stat-label">Latency</span>
            </div>
            <div className="stat-item">
              <span className={`stat-value conn-state-${connState}`}>{statusLabel}</span>
              <span className="stat-label">Status</span>
            </div>
          </div>

          <div className="connect-area">
            {connState !== 'connected' ? (
              <button className="btn-connect" onClick={connect} disabled={connState === 'connecting'}>
                {connState === 'connecting' ? (
                  <><span className="spinner-sm" />Connecting…</>
                ) : (
                  <>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3" /></svg>
                    Connect
                  </>
                )}
              </button>
            ) : (
              <button className="btn-disconnect" onClick={disconnect}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></svg>
                Disconnect
              </button>
            )}
          </div>
        </div>

        {/* Right: Chat panel */}
        <div className="chat-panel">
          <div className="chat-messages">
            {messages.map(m => (
              <div key={m.id} className={`message ${m.role}-message`}>
                {m.role !== 'system' && (
                  <div className="message-avatar">
                    {m.role === 'assistant' ? (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M12 2a5 5 0 0 1 5 5v3a5 5 0 0 1-10 0V7a5 5 0 0 1 5-5Z" />
                        <path d="M17 10v1a5 5 0 0 1-10 0v-1" />
                      </svg>
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                        <circle cx="12" cy="7" r="4" />
                      </svg>
                    )}
                  </div>
                )}
                <div className="message-content">
                  {m.role !== 'system' && (
                    <div className="message-header">
                      <span className="message-name">{m.role === 'assistant' ? 'AI Assistant' : 'You'}</span>
                      <span className="message-time">{m.time}</span>
                    </div>
                  )}
                  <div
                    className="message-text"
                    dangerouslySetInnerHTML={{ __html: formatText(m.text) }}
                  />
                </div>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>

          <div className="input-area">
            <div className="voice-hint">
              {connState === 'connected'
                ? <><span className="mic-pulse" />Listening — speak now</>
                : 'Connect to start the voice conversation'}
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

function formatText(text: string): string {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')
}
