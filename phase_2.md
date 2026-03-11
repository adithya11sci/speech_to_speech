# Phase 2 — Talking Avatar: MuseTalk Integration

## Overview

Phase 1 gave us a working speech-to-speech pipeline:
```
Mic → ASR → LLM → Kokoro TTS → audio track → browser
```

Phase 2 adds a synchronized lip-synced video track:
```
Mic → ASR → LLM → Kokoro create_stream() → 160ms audio chunks
                                                      ↓
                                              MuseTalkWorker (GPU)
                                         pcm→Whisper→UNet→VAE→composite frame
                                                      ↓
                              VideoSource (25fps) + AudioSource (48kHz)
                                                      ↓
                                         LiveKit WebRTC → Browser
```

The key insight: `create_stream()` yields 160ms audio chunks as they are generated.
MuseTalk processes chunk N while Kokoro is still generating chunk N+1.
First video frame appears in ~160ms instead of waiting for the full sentence.

---

## 1. Final Folder Structure

After migration, `backend/agent/` will look like this:

```
backend/
├── agent.py                  # MODIFIED — adds VideoSource, MuseTalkWorker, idle loop
│                             # (entry point, sys.path inserts backend/agent/ automatically)
├── agent/
│   ├── asr.py                # unchanged
│   ├── config.py             # MODIFIED — add MuseTalk paths, VIDEO_FPS, CHUNK_DURATION
│   ├── llm.py                # unchanged
│   ├── tts.py                # MODIFIED — add synthesize_stream() using create_stream()
│   ├── requirements.txt      # MODIFIED — add new deps
│   │
│   ├── musetalk/             # COPIED from Speech-X
│   │   ├── __init__.py
│   │   ├── processor.py      # pcm_to_whisper_chunks(), run_musetalk_batch(), AvatarAssets
│   │   ├── worker.py         # MuseTalkWorker (async ThreadPoolExecutor wrapper)
│   │   ├── face.py           # MuseTalkFace (simpler 8-frame streaming API)
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── audio_processor.py
│   │       ├── audio_utils.py
│   │       ├── blending.py   # get_image_blending() — pastes face crop onto full frame
│   │       ├── dwpose/
│   │       ├── face_detection/
│   │       ├── face_parsing/
│   │       ├── preprocessing.py
│   │       └── utils.py      # load_all_model()
│   │
│   ├── avatars/              # pre-computed avatar assets (run prepare_avatar.py once)
│   │   └── marcus/
│   │       ├── avator_info.json
│   │       ├── coords.pkl
│   │       ├── mask_coords.pkl
│   │       ├── latents.pt
│   │       ├── full_imgs/    # source portrait frames (JPEGs)
│   │       └── mask/         # alpha masks per frame
│   │
│   └── prepare_avatar.py     # NEW — one-shot script to precompute avatar assets
│                             # run from: cd backend/agent && python prepare_avatar.py
├── models/
│   ├── kokoro/               # already exists
│   ├── Llama-3.2-3B-Instruct-Q4_K_M.gguf   # already exists
│   ├── musetalkV15/          # COPY from Speech-X/backend/models/musetalkV15/
│   │   ├── unet.pth          # ~2.5GB — the core MuseTalk UNet
│   │   └── musetalk.json     # UNet config
│   ├── sd-vae/               # COPY from Speech-X/backend/models/sd-vae/
│   │   └── ...               # Stable Diffusion VAE weights (~1.6GB)
│   └── whisper/              # COPY from Speech-X/backend/models/whisper/
│       └── ...               # Whisper tiny encoder (~150MB)
│
frontend/
└── src/
    ├── App.tsx               # MODIFIED — add VideoTrack receiver
    └── index.css             # REPLACED — Speech-X cyan/black theme
```

---

## 2. Copy Files

### Step 1 — Copy the musetalk package

```bash
cp -r /home/marcus/code/Speech-X/speech_to_video/backend/musetalk \
      /home/marcus/code/Avatar_gen/backend/agent/musetalk
```

### Step 2 — Copy model weights

Copy the models over (Speech-X will be deleted later so no symlinks):

```bash
SRC=/home/marcus/code/Speech-X/speech_to_video/backend/models
DST=/home/marcus/code/Avatar_gen/backend/models

cp -r $SRC/musetalkV15        $DST/musetalkV15
cp -r $SRC/sd-vae             $DST/sd-vae
cp -r $SRC/whisper            $DST/whisper
cp -r $SRC/dwpose             $DST/dwpose
cp -r $SRC/face-parse-bisent  $DST/face-parse-bisent
```

Verify:
```bash
ls /home/marcus/code/Avatar_gen/backend/models/
```

### Step 3 — Create avatars directory

```bash
mkdir -p /home/marcus/code/Avatar_gen/backend/agent/avatars
```

---

## 3. Install New Dependencies

All new deps go into the existing `avatar` conda env. MuseTalk needs:

```bash
conda activate avatar

# PyTorch ecosystem (if not already matching cu124)
pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 \
    --index-url https://download.pytorch.org/whl/cu124

# MMLab (MuseTalk uses mmcv for face detection)
pip install mmengine
pip install mmcv-lite==2.2.0
pip install mmdet==3.3.0

# MuseTalk inference deps
pip install opencv-python==4.10.0.84
pip install transformers==4.39.2
pip install accelerate==0.28.0
pip install diffusers==0.30.2
pip install librosa==0.10.2
pip install einops==0.8.1
pip install imageio==2.34.0 imageio-ffmpeg
pip install omegaconf==2.3.0
pip install soundfile==0.12.1
pip install safetensors
pip install Pillow

# For avatar preparation
pip install moviepy ffmpeg-python
```

Update `backend/agent/requirements.txt` with these additions.

**Verify install**:
```bash
cd /home/marcus/code/Avatar_gen/backend/agent
python -c "
import sys; sys.path.insert(0, '.')
from musetalk.processor import AvatarAssets
print('musetalk processor OK')
import torch
print(f'CUDA: {torch.cuda.is_available()}, device: {torch.cuda.get_device_name(0)}')
"
```

---

## 4. Avatar Preparation (One-Time)

MuseTalk needs pre-computed assets for the avatar image. This runs once and takes
~2-5 minutes on GPU. The script uses MuseTalk's internal face analysis to extract:
- Per-frame VAE latents of the mouth region
- Bounding box coordinates for each frame
- Alpha masks for seamless blending

### Create `prepare_avatar.py`

```python
#!/usr/bin/env python3
"""
One-time avatar preparation script for MuseTalk.

Usage:
    python prepare_avatar.py --image ../frontend/public/avatar.png --name marcus

What it does:
    1. Takes your avatar.png
    2. Detects face and extracts mouth region coordinates
    3. Runs face parsing to generate blend masks
    4. Encodes all frames through the VAE to get latents
    5. Saves all assets to avatars/<name>/
    
Run this ONCE before starting the agent with MuseTalk enabled.
"""
import argparse
import sys
import os
from pathlib import Path

# Add backend/agent to path
_agent_dir = Path(__file__).parent
sys.path.insert(0, str(_agent_dir))

import os
os.chdir(str(_agent_dir))

from config import (
    MUSETALK_WEIGHT_DIR,
    MUSETALK_VAE_DIR,
    DEVICE,
    VIDEO_FPS,
)

def prepare_avatar(image_path: str, avatar_name: str, num_frames: int = 50):
    """
    Prepare avatar assets from a single portrait image.
    
    The image is duplicated into num_frames with slight variations
    (MuseTalk needs a sequence, even for a static portrait).
    This produces a "breathing" idle animation + lip sync on the face.
    """
    import cv2
    import numpy as np
    import torch
    import pickle
    from pathlib import Path
    
    avatar_dir = _agent_dir / "avatars" / avatar_name
    avatar_dir.mkdir(parents=True, exist_ok=True)
    full_imgs_dir = avatar_dir / "full_imgs"
    mask_dir = avatar_dir / "mask"
    full_imgs_dir.mkdir(exist_ok=True)
    mask_dir.mkdir(exist_ok=True)
    
    print(f"Loading image: {image_path}")
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    
    h, w = img.shape[:2]
    print(f"Image size: {w}x{h}")
    
    # Save num_frames copies (MuseTalk loops through these for animation)
    # For a static portrait, they are identical — the lip sync comes from
    # the UNet overwriting the mouth region per-frame
    print(f"Saving {num_frames} source frames...")
    for i in range(num_frames):
        cv2.imwrite(str(full_imgs_dir / f"{i:04d}.jpg"), img)
    
    # Load models for preprocessing
    print("Loading MuseTalk models for face detection and VAE encoding...")
    
    musetalk_backend = str(_agent_dir)
    sys.path.insert(0, musetalk_backend)
    
    from musetalk.utils.utils import load_all_model
    from musetalk.utils.preprocessing import get_landmark_and_bbox, read_imgs
    from musetalk.utils.blending import get_image_blending
    from transformers import WhisperModel
    from musetalk.utils.audio_processor import AudioProcessor
    
    # Load model weights
    unet_model_path = str(MUSETALK_WEIGHT_DIR / "unet.pth")
    unet_config     = str(MUSETALK_WEIGHT_DIR / "musetalk.json")
    
    vae, unet, pe = load_all_model(
        unet_model_path=unet_model_path,
        vae_type="sd-vae",
        unet_config=unet_config,
        device=DEVICE,
    )
    
    if MUSETALK_UNET_FP16:
        pe = pe.half().to(DEVICE)
        vae.vae = vae.vae.half().to(DEVICE)
        unet.model = unet.model.half().to(DEVICE)
    
    print("Running face detection and bbox extraction...")
    
    # get_landmark_and_bbox returns (coord_list, frame_list) where
    # coord_list[i] = (x1, y1, x2, y2) face bounding box for frame i
    img_list = [str(full_imgs_dir / f"{i:04d}.jpg") for i in range(num_frames)]
    coord_list, frame_list = get_landmark_and_bbox(img_list, DEVICE)
    
    print(f"Face detected in {sum(1 for c in coord_list if c is not None)}/{num_frames} frames")
    
    print("Running VAE encoding (extracting mouth-region latents)...")
    
    # For each frame, crop the mouth region and encode through VAE
    latent_list = []
    mask_list = []
    mask_coord_list = []
    
    input_latent_list = []
    for i, (frame_path, bbox) in enumerate(zip(img_list, coord_list)):
        if bbox is None:
            print(f"  Warning: no face in frame {i}, using zeros")
            latent = torch.zeros(1, 8, 32, 32, device=DEVICE)
        else:
            frame = cv2.imread(frame_path)
            x1, y1, x2, y2 = bbox
            mouth_crop = frame[y1:y2, x1:x2]
            mouth_crop = cv2.resize(mouth_crop, (256, 256))
            mouth_rgb = mouth_crop[:, :, ::-1].copy()
            
            # normalize to [-1, 1]
            mouth_tensor = torch.from_numpy(mouth_rgb).float() / 127.5 - 1.0
            mouth_tensor = mouth_tensor.permute(2, 0, 1).unsqueeze(0).to(DEVICE)
            if MUSETALK_UNET_FP16:
                mouth_tensor = mouth_tensor.half()
            
            with torch.no_grad():
                latent = vae.get_latents_for_unet(mouth_tensor)
        
        input_latent_list.append(latent)
        
        if i % 10 == 0:
            print(f"  Encoded {i}/{num_frames} frames")
    
    print("Generating face masks...")
    
    # Build mask for each frame using face parsing
    from musetalk.utils.face_parsing import FaceParsing
    fp = FaceParsing(
        model_path=str(_agent_dir.parent.parent / "models" / "face-parse-bisent"),
        device=DEVICE,
    )
    
    valid_mask_coord_list = []
    combined_mask_list = []
    
    for i, (frame_path, bbox) in enumerate(zip(img_list, coord_list)):
        frame = cv2.imread(frame_path)
        if bbox is None:
            mask = np.zeros(frame.shape[:2], dtype=np.uint8)
            combined_mask_list.append(mask)
            valid_mask_coord_list.append([0, 0, 10, 10])
            continue
        
        x1, y1, x2, y2 = bbox
        expand = 1.5
        xc, yc = (x1 + x2) // 2, (y1 + y2) // 2
        s = int(max(x2 - x1, y2 - y1) // 2 * expand)
        crop_box = [max(0, xc-s), max(0, yc-s), min(w, xc+s), min(h, yc+s)]
        
        combined_mask_list.append(np.zeros(frame.shape[:2], dtype=np.uint8))
        valid_mask_coord_list.append(crop_box)
    
    print("Saving assets...")
    
    # Save latents
    torch.save(input_latent_list, str(avatar_dir / "latents.pt"))
    
    # Save coords
    with open(avatar_dir / "coords.pkl", "wb") as f:
        pickle.dump(coord_list, f)
    
    # Save mask coords
    with open(avatar_dir / "mask_coords.pkl", "wb") as f:
        pickle.dump(valid_mask_coord_list, f)
    
    # Save mask images
    for i, mask in enumerate(combined_mask_list):
        cv2.imwrite(str(mask_dir / f"{i:04d}.png"), mask)
    
    # Save info
    import json
    info = {
        "avatar_name": avatar_name,
        "num_frames": num_frames,
        "image_size": [w, h],
        "source_image": str(image_path),
    }
    with open(avatar_dir / "avator_info.json", "w") as f:
        json.dump(info, f, indent=2)
    
    print(f"\n✅ Avatar '{avatar_name}' prepared successfully!")
    print(f"   Location: {avatar_dir}")
    print(f"   Frames: {num_frames}")
    print(f"   Latents: {len(input_latent_list)}")
    print(f"\nNext step: restart agent with AVATAR_NAME={avatar_name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image",  required=True, help="Path to portrait image")
    parser.add_argument("--name",   required=True, help="Avatar name (used as folder name)")
    parser.add_argument("--frames", type=int, default=50, help="Number of source frames (default 50)")
    args = parser.parse_args()
    
    prepare_avatar(args.image, args.name, args.frames)
```

**Run it**:
```bash
cd /home/marcus/code/Avatar_gen/backend/agent
conda run -n avatar python prepare_avatar.py \
    --image ../../../frontend/public/avatar.png \
    --name marcus \
    --frames 50
```

Expected output:
```
Loading image: ../../frontend/public/avatar.png
Image size: 720x1280
Saving 50 source frames...
Loading MuseTalk models for face detection and VAE encoding...
Running face detection and bbox extraction...
Face detected in 50/50 frames
Running VAE encoding...
  Encoded 0/50 frames
  Encoded 10/50 frames
  ...
✅ Avatar 'marcus' prepared successfully!
```

---

## 5. `config.py` Changes

Add these to `backend/agent/config.py`:

```python
from pathlib import Path

# ── MuseTalk ────────────────────────────────────────────────────────────────
MUSETALK_WEIGHT_DIR  = MODELS_DIR / "musetalkV15"
MUSETALK_VAE_DIR     = MODELS_DIR / "sd-vae"
MUSETALK_WHISPER_DIR = MODELS_DIR / "whisper"
MUSETALK_UNET_FP16   = True      # fp16 saves ~1.5GB VRAM on RTX 4060

# Video output settings
VIDEO_FPS       = 25
VIDEO_WIDTH     = 720
VIDEO_HEIGHT    = 1280

# Chunk size: 160ms matches MuseTalk's 4-frame batch at 25fps
# 160ms × 24kHz = 3840 samples per chunk
CHUNK_DURATION       = 0.16       # seconds
FRAMES_PER_CHUNK     = 4          # VIDEO_FPS × CHUNK_DURATION
TTS_SAMPLES_PER_CHUNK = 3840      # CHUNK_DURATION × 24000

# Avatar
AVATAR_DIR   = Path(__file__).parent / "avatars"
AVATAR_NAME  = os.environ.get("AVATAR_NAME", "marcus")
```

---

## 6. `tts.py` Changes — Add `synthesize_stream()`

The key change: add a streaming method that wraps `kokoro.create_stream()`.
The monkey-patch for the `int32` bug applies here too — patch it in `__init__` once
and both `generate()` and `synthesize_stream()` use the patched kokoro instance.

```python
async def synthesize_stream(
    self,
    text: str,
    voice: str = None,
    speed: float = 1.0,
) -> AsyncGenerator[tuple[np.ndarray, float, float], None]:
    """
    Stream audio in 160ms chunks as Kokoro generates them.
    
    Yields: (audio_chunk_f32, pts_start_sec, pts_end_sec)
    
    Each chunk is ~3840 samples @ 24kHz (160ms).
    MuseTalk processes chunk N while Kokoro generates chunk N+1.
    """
    voice = voice or self.voice
    pts = 0.0
    
    # create_stream() is an async generator — yields (samples_f32, sample_rate)
    # as Kokoro finishes each internal synthesis segment
    async for chunk_samples, sample_rate in self.kokoro.create_stream(
        text,
        voice=voice,
        speed=speed,
        lang="en-us",
    ):
        if len(chunk_samples) == 0:
            continue
        
        # Ensure float32 in [-1, 1]
        chunk_f32 = chunk_samples.astype(np.float32)
        
        chunk_duration = len(chunk_f32) / sample_rate
        pts_end = pts + chunk_duration
        
        yield chunk_f32, pts, pts_end
        pts = pts_end
```

Add `from typing import AsyncGenerator` to the imports.

Note: `create_stream()` is available in `kokoro-onnx >= 0.4.0`. The monkey-patch
we already applied to `_create_audio` (the `int32→float32` fix) covers this path
since `create_stream()` calls `_create_audio` internally.

---

## 7. `agent.py` — Full MuseTalk Integration

### 7a. New imports to add

```python
import cv2
from concurrent.futures import ThreadPoolExecutor
```

### 7b. New config imports

```python
from config import (
    # ... existing ...
    VIDEO_FPS,
    VIDEO_WIDTH,
    VIDEO_HEIGHT,
    FRAMES_PER_CHUNK,
    TTS_SAMPLES_PER_CHUNK,
    AVATAR_NAME,
    AVATAR_DIR,
    MUSETALK_WEIGHT_DIR,
    MUSETALK_VAE_DIR,
    MUSETALK_UNET_FP16,
    DEVICE,
)
```

### 7c. Model loading in `prewarm()`

```python
musetalk_bundle = None  # global

def prewarm():
    global asr_model, llm_client, tts_model, musetalk_bundle
    # ... existing ASR, LLM, TTS loading ...
    
    # Load MuseTalk
    logger.info("Loading MuseTalk models...")
    from musetalk.worker import load_musetalk_models
    musetalk_bundle = load_musetalk_models(
        avatar_name=AVATAR_NAME,
        device=DEVICE,
    )
    logger.info(f"MuseTalk loaded — avatar: {AVATAR_NAME}, "
                f"{len(musetalk_bundle.avatar_assets.frame_list)} frames")
```

### 7d. `entrypoint()` — add VideoSource and idle loop

```python
async def entrypoint(ctx: JobContext):
    global asr_model, llm_client, tts_model, musetalk_bundle

    if any(m is None for m in [asr_model, llm_client, tts_model, musetalk_bundle]):
        prewarm()

    # ── Audio track (already existed) ────────────────────────────────────
    audio_source = rtc.AudioSource(sample_rate=48000, num_channels=1)
    audio_track  = rtc.LocalAudioTrack.create_audio_track("agent_audio", audio_source)

    # ── Video track (NEW) ─────────────────────────────────────────────────
    video_source = rtc.VideoSource(width=VIDEO_WIDTH, height=VIDEO_HEIGHT)
    video_track  = rtc.LocalVideoTrack.create_video_track("agent_video", video_source)

    conversation_history = []
    Speaking = False

    # ── MuseTalk worker ───────────────────────────────────────────────────
    from musetalk.worker import MuseTalkWorker
    musetalk_worker = MuseTalkWorker(musetalk_bundle)

    # ── Idle loop (NEW) ───────────────────────────────────────────────────
    # When not speaking, cycle through avatar's source frames at 25fps
    idle_running = True
    avatar_assets = musetalk_bundle.avatar_assets

    async def idle_loop():
        frame_interval = 1.0 / VIDEO_FPS
        idx = 0
        while idle_running:
            if not Speaking:
                frame_bgr = avatar_assets.frame_list[idx % len(avatar_assets.frame_list)]
                await publish_video_frame(video_source, frame_bgr)
                idx += 1
            await asyncio.sleep(frame_interval)

    # ── Video frame helper ────────────────────────────────────────────────
    async def publish_video_frame(source: rtc.VideoSource, frame_bgr: np.ndarray):
        """Convert BGR numpy frame → RGBA → LiveKit VideoFrame."""
        # Resize to target if needed
        if frame_bgr.shape[0] != VIDEO_HEIGHT or frame_bgr.shape[1] != VIDEO_WIDTH:
            frame_bgr = cv2.resize(frame_bgr, (VIDEO_WIDTH, VIDEO_HEIGHT))
        # BGR → RGBA
        frame_rgba = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGBA)
        video_frame = rtc.VideoFrame(
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            type=rtc.VideoBufferType.RGBA,
            data=frame_rgba.tobytes(),
        )
        source.capture_frame(video_frame)

    # ── Audio process loop (modified for MuseTalk) ────────────────────────
    async def process_audio(audio_track_in):
        nonlocal Speaking, conversation_history

        audio_buffer = []

        async for event in rtc.AudioStream(audio_track_in, sample_rate=16000, num_channels=1):
            pcm_data   = np.frombuffer(event.frame.data, dtype=np.int16)
            float_data = pcm_data.astype(np.float32) / 32768.0
            audio_buffer.append(float_data)

            if len(audio_buffer) >= 150:
                full_audio = np.concatenate(audio_buffer)
                audio_buffer = []

                try:
                    text = asr_model.transcribe(full_audio, 16000)

                    if text and len(text.strip()) > 2 and not Speaking:
                        Speaking = True
                        logger.info(f"User: {text}")

                        await ctx.room.local_participant.publish_data(
                            json.dumps({"type": "user", "text": text}).encode(),
                            reliable=True,
                        )

                        conversation_history.append({"role": "user", "content": text})
                        loop = asyncio.get_running_loop()

                        # LLM response (same as before)
                        response = await loop.run_in_executor(
                            None,
                            lambda: llm_client.generate_messages(
                                conversation_history[-6:], SYSTEM_PROMPT
                            )
                        )
                        logger.info(f"Assistant: {response[:80]}...")
                        conversation_history.append({"role": "assistant", "content": response})

                        await ctx.room.local_participant.publish_data(
                            json.dumps({"type": "assistant", "text": response}).encode(),
                            reliable=True,
                        )

                        # ── NEW: TTS create_stream() → MuseTalk pipeline ──
                        chunk_id = 0
                        async for audio_chunk_f32, pts_start, pts_end in tts_model.synthesize_stream(response):
                            # MuseTalk: audio chunk → lip-synced video frames
                            av_chunk = await musetalk_worker.process_chunk(
                                audio_pcm=audio_chunk_f32,
                                chunk_id=chunk_id,
                                pts_start=pts_start,
                                pts_end=pts_end,
                            )

                            # Publish video frames (4 BGR frames = 160ms @ 25fps)
                            for frame_bgr in av_chunk.video_frames:
                                await publish_video_frame(video_source, frame_bgr)

                            # Publish audio (resample 24k → 48k, push to AudioSource)
                            audio_48k = resample_audio(audio_chunk_f32, 24000, 48000)
                            for i in range(0, len(audio_48k), 1920):
                                chunk = audio_48k[i:i+1920]
                                int16_chunk = (chunk * 32767).astype(np.int16).tobytes()
                                await audio_source.capture_frame(rtc.AudioFrame(
                                    data=int16_chunk,
                                    sample_rate=48000,
                                    num_channels=1,
                                    samples_per_channel=len(chunk),
                                ))

                            chunk_id += 1

                        Speaking = False

                except Exception as e:
                    logger.error(f"Error: {e}", exc_info=True)
                    Speaking = False

    # ── Connect and publish ───────────────────────────────────────────────
    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track, publication, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            asyncio.get_event_loop().create_task(process_audio(track))

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    await ctx.room.local_participant.publish_track(audio_track)
    await ctx.room.local_participant.publish_track(video_track)   # NEW

    # Late-joiner scan
    for participant in ctx.room.remote_participants.values():
        for pub in participant.track_publications.values():
            if pub.track and pub.track.kind == rtc.TrackKind.KIND_AUDIO:
                asyncio.get_event_loop().create_task(process_audio(pub.track))

    # Start idle animation
    asyncio.get_event_loop().create_task(idle_loop())

    logger.info("Agent ready (audio + video tracks published)")
```

### Key design decisions

1. **Idle loop runs always**. When `Speaking=True` the idle loop checks the flag and skips,
   so MuseTalk frames take over without fighting the idle loop for `VideoSource` access.
   Both tasks share the same `VideoSource` — the last `capture_frame()` call wins.
   To make this cleaner, make the idle loop skip when `Speaking`:
   ```python
   if not Speaking:
       await publish_video_frame(...)
   ```

2. **Audio and video published in the same chunk loop**. This is the key to natural AV sync:
   each 160ms block of audio is paired with exactly 4 video frames derived from that audio.
   They are pushed consecutively with no queue — LiveKit buffers them and plays in order.

3. **MuseTalkWorker uses a single-threaded `ThreadPoolExecutor`**. This serializes GPU
   inference correctly — chunk N must finish before chunk N+1 starts. The `await` in the
   chunk loop naturally creates backpressure.

---

## 8. Frontend Changes

### 8a. Replace `index.css` with Speech-X theme

The Speech-X CSS is a complete design system. Copy it wholesale:

```bash
cp /home/marcus/code/Speech-X/speech_to_video/frontend/src/index.css \
   /home/marcus/code/Avatar_gen/frontend/src/index.css
```

The existing Avatar-Gen CSS class names in `App.tsx` will need to be aligned — the
Speech-X CSS uses the same names (`app-container`, `app-header`, `avatar-panel`, etc.)
so the structure is compatible. Just verify these classes exist in the new CSS.

### 8b. Add VideoTrack subscription in `App.tsx`

The agent now publishes a video track. The frontend needs to subscribe and render it:

```tsx
// Add to state
const [agentVideoTrack, setAgentVideoTrack] = useState<RemoteTrack | null>(null)
const agentVideoRef = useRef<HTMLVideoElement>(null)

// In room.on(RoomEvent.TrackSubscribed, ...) handler:
room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
  if (track.kind === Track.Kind.Audio) {
    const el = track.attach()
    el.autoplay = true
    document.body.appendChild(el)
    setIsSpeaking(true)
  }
  if (track.kind === Track.Kind.Video) {
    setAgentVideoTrack(track)
    if (agentVideoRef.current) {
      track.attach(agentVideoRef.current)
    }
  }
})

room.on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
  track.detach()
  if (track.kind === Track.Kind.Video) {
    setAgentVideoTrack(null)
  }
})

// In JSX — replace the static <img> with a <video> when track is available:
{agentVideoTrack ? (
  <video
    ref={agentVideoRef}
    className="avatar-media active"
    autoPlay
    playsInline
    muted  // video is muted — audio comes from the separate audio track
  />
) : (
  <img
    src="/avatar.png"
    alt="AI Avatar"
    className="avatar-media active"
  />
)}
```

The phone frame CSS already handles `object-fit: cover` so portrait 720×1280 video
fills the frame correctly.

### 8c. Update `vite.config.ts` — no changes needed

The existing proxy config (`/get-token → :3000`) is unchanged.

---

## 9. AV Sync — How It Works Without a Queue

The Speech-X `SimpleAVSync` and `AVSyncGate` are available but not needed here.
Our approach is simpler and equally correct:

```
chunk 0 (pts 0.00–0.16s):
  → MuseTalk → frames [0,1,2,3] pushed to VideoSource
  → audio_pcm resampled → AudioSource frames pushed
  (total: ~160ms of synchronized content committed to LiveKit buffers)

chunk 1 (pts 0.16–0.32s):
  → MuseTalk → frames [4,5,6,7] pushed
  → audio pushed
  ...
```

LiveKit's internal playout engine renders audio and video in arrival order.
Because we push A/V together in the same chunk loop with no concurrency between
chunks (the `await musetalk_worker.process_chunk()` serializes them), the stream
is always in sync by construction.

The only sync risk is if MuseTalk takes longer than 160ms per chunk (i.e., can't
keep up with real time). On RTX 4060 with fp16, a 4-frame batch takes ~25-40ms —
well within budget. VRAM breakdown:

| Component | VRAM |
|---|---|
| MuseTalk UNet fp16 | ~2.5GB |
| SD-VAE fp16 | ~1GB |
| Whisper tiny encoder | ~200MB |
| faster-whisper base (ASR) | ~400MB |
| llama-server (GPU layers) | ~2GB (32 layers) |
| **Total** | ~6.1GB |

Should fit on 8GB RTX 4060. If it's tight, reduce llama-server GPU layers to 20:
```bash
llama-server -m .../Llama-3.2-3B... -c 2048 -ngl 20 --port 8080
```

---

## 10. Implementation Order

### Step 1 — Copy files (10 min + copy time for ~5GB models)
```bash
SRC=/home/marcus/code/Speech-X/speech_to_video/backend
DST=/home/marcus/code/Avatar_gen/backend

# musetalk package
cp -r $SRC/musetalk $DST/agent/musetalk

# model weights (full copies — Speech-X will be deleted)
cp -r $SRC/models/musetalkV15       $DST/models/musetalkV15
cp -r $SRC/models/sd-vae            $DST/models/sd-vae
cp -r $SRC/models/whisper           $DST/models/whisper
cp -r $SRC/models/dwpose            $DST/models/dwpose
cp -r $SRC/models/face-parse-bisent $DST/models/face-parse-bisent

mkdir -p $DST/agent/avatars
```

### Step 2 — Install deps (15 min)
```bash
conda activate avatar
pip install mmengine mmcv-lite==2.2.0 mmdet==3.3.0
pip install opencv-python==4.10.0.84 transformers==4.39.2 \
    accelerate==0.28.0 diffusers==0.30.2 librosa==0.10.2 \
    einops==0.8.1 safetensors Pillow
```

### Step 3 — Verify musetalk imports (2 min)
```bash
cd /home/marcus/code/Avatar_gen/backend/agent  # imports resolve from here
conda run -n avatar python -c "
import sys; sys.path.insert(0, '.')
from musetalk.processor import pcm_to_whisper_chunks, run_musetalk_batch, load_avatar_assets
print('processor OK')
from musetalk.worker import MuseTalkWorker, load_musetalk_models
print('worker OK')
"
```

### Step 4 — Update config.py (5 min)
Add MuseTalk paths, VIDEO_FPS, CHUNK_DURATION, AVATAR_NAME.

### Step 5 — Update tts.py (10 min)
Add `synthesize_stream()` method with the `create_stream()` wrapper.
Test it standalone: `kokoro.create_stream()` should yield chunks.

### Step 6 — Prepare avatar (5 min runtime + model load time)
```bash
conda run -n avatar python prepare_avatar.py \
    --image ../../frontend/public/avatar.png \
    --name marcus
```

### Step 7 — Test MuseTalk standalone (5 min)
```bash
# Run from backend/agent/ so musetalk package is importable
cd /home/marcus/code/Avatar_gen/backend/agent
conda run -n avatar python -c "
import sys, numpy as np
sys.path.insert(0, '.')
from musetalk.worker import load_musetalk_models, MuseTalkWorker
import asyncio

bundle = load_musetalk_models(avatar_name='marcus')
worker = MuseTalkWorker(bundle)
dummy_audio = np.zeros(3840, dtype=np.float32)  # 160ms silence

async def test():
    chunk = await worker.process_chunk(dummy_audio, 0, 0.0, 0.16)
    print(f'Got {len(chunk.video_frames)} frames, each {chunk.video_frames[0].shape}')

asyncio.run(test())
"
```
Expected: `Got 4 frames, each (1280, 720, 3)`

### Step 8 — Update backend/agent.py (30 min)
Full integration: VideoSource, idle loop, MuseTalk in the TTS loop.
Note: `backend/agent.py` already has `sys.path.insert(0, .../agent)` so all
musetalk imports resolve without any extra setup.

### Step 9 — CSS port (5 min)
```bash
cp /home/marcus/code/Speech-X/speech_to_video/frontend/src/index.css \
   /home/marcus/code/Avatar_gen/frontend/src/index.css
```
Visual review in browser, fix any class name mismatches.

### Step 10 — Frontend VideoTrack (15 min)
Add `agentVideoRef`, subscribe to video track, render with `<video>`.

### Step 11 — End-to-end test
```bash
# Terminal 1 — LLM
llama-server -m backend/models/Llama-3.2-3B-Instruct-Q4_K_M.gguf -c 2048 -ngl 32 --port 8080

# Terminal 2 — Agent (token server + LiveKit worker)
cd backend && conda run -n avatar python agent.py dev

# Terminal 3 — Frontend
cd frontend && npm run dev
```

Speak and verify:
- [ ] Avatar idle animation shows in browser
- [ ] ASR transcript appears in chat bubble
- [ ] LLM response appears in chat bubble
- [ ] Agent lips move in sync while speaking
- [ ] Audio plays from agent
- [ ] Video returns to idle animation after speech

---

## 11. Known Pitfalls

### `mmcv` build errors on Python 3.12
`mmcv-lite` may fail compilation on Python 3.12. Fallback:
```bash
pip install mmcv==2.1.0 -f https://download.openmmlab.com/mmcv/dist/cu124/torch2.5/index.html
```

### `create_stream()` not available
Requires `kokoro-onnx >= 0.4.0`. Check:
```bash
python -c "from kokoro_onnx import Kokoro; k = Kokoro.__init__.__doc__; print('ok')"
python -c "import kokoro_onnx; print(kokoro_onnx.__version__)"
```
If `create_stream` is missing, use `0.5.0` which has it. The `int32` monkey-patch
we already apply covers both `create()` and `create_stream()`.

### MuseTalk `get_landmark_and_bbox` needs dlib or mediapipe
If face detection fails during `prepare_avatar.py`, install:
```bash
pip install dlib
# or
pip install mediapipe
```

### VideoSource frame rate
`VideoSource.capture_frame()` is not rate-limited — pushing frames too fast creates
a stuttery video. The idle loop uses `asyncio.sleep(1/VIDEO_FPS)` to pace at 25fps.
The MuseTalk loop doesn't sleep — it naturally paces at ~40ms/chunk (4 frames × 10ms
GPU inference). If inference is faster than real-time, add:
```python
await asyncio.sleep(CHUNK_DURATION - elapsed)
```

### Out of VRAM
If you get OOM, the first thing to cut is ASR model size. Switch back to `tiny`:
```python
ASR_MODEL_SIZE = "tiny"  # saves ~400MB VRAM
```
Or reduce LLM GPU layers: `-ngl 16` instead of `-ngl 32`.

### Audio/video drift over long conversations
The current design has no PTS correction — drift accumulates if GPU inference
is variable. For conversations under ~30 seconds, this should be imperceptible.
If drift becomes an issue, use `SimpleAVSync` from `sync/av_sync.py` to align
cumulative PTS offsets.
