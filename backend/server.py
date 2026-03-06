from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from livekit.api import AccessToken, VideoGrants

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LIVEKIT_API_KEY = "devkey"
LIVEKIT_API_SECRET = "secret"


@app.get("/")
async def root():
    return FileResponse("frontend/index.html")


@app.post("/get-token")
async def get_token(request: dict):
    room_name = request.get("roomName", "voice-room")
    identity = request.get("identity", "user")

    token = (
        AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_grants(VideoGrants(room_join=True, room=room_name))
        .to_jwt()
    )

    return {"token": token}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
