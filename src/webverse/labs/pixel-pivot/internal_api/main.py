import os
import re
import subprocess
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "APV_INTERNAL_6d7f9c2b4b")

app = FastAPI(title="UbiHard Internal API", version="2.3.0", docs_url=None, redoc_url=None)

# Block ; & | and ANY whitespace (spaces, tabs, newlines, etc.)
FORBIDDEN_IN_GAMEKEY = re.compile(r"[;&|]")


def validate_game_key(game_key: str) -> str:
    if not isinstance(game_key, str):
        raise HTTPException(
            status_code=400,
            detail="Invalid 'game' value: must be a string."
        )

    game_key = game_key.strip()

    if not game_key:
        raise HTTPException(
            status_code=400,
            detail="Missing 'game' value in JSON body."
        )

    # Blacklist requested by you
    if FORBIDDEN_IN_GAMEKEY.search(game_key):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid game."
            )
        )

    return game_key


def require_key(request: Request) -> None:
    """
    Gate internal API endpoints behind an API key.
    Be more verbose when missing, so it isn't pure guesswork.
    """
    provided = request.headers.get("X-API-Key")

    # Missing header -> explicit guidance
    if not provided:
        raise HTTPException(
            status_code=401,
            detail=(
                "Missing required header: X-API-Key. "
                "This endpoint is part of an internal integration and requires an API key.\n"
                "Example:\n"
                "  curl -H 'X-API-Key: <key>' -H 'Content-Type: application/json' "
                "-d '{\"game\":\"fortnite\"}' http://internal-api.ubihard.local/api/v1/ops/probe"
            ),
        )

    # Wrong header -> still clear, but not leaking the key
    if provided != INTERNAL_API_KEY:
        raise HTTPException(
            status_code=403,
            detail=(
                "Invalid X-API-Key. "
                "Provide a valid internal integration key in the X-API-Key header."
            ),
        )


@app.get("/api/v1/health")
def health():
    return {"ok": True, "service": "internal-api", "version": "2.3.0"}


@app.post("/api/v1/ops/probe")
async def probe(request: Request):
    """
    Training vuln: command injection (intentionally vulnerable).
    Intended behavior: check processes for a game key.
    """
    require_key(request)

    body = await request.json()
    game = validate_game_key(body.get("game", ""))

    # VULNERABILITY (training): user input concatenated into a shell command
    cmd = f"ps aux | grep {game}"

    result = subprocess.run(
        cmd,
        shell=True,
        text=True,
        capture_output=True
    )

    out = (result.stdout or "") + (result.stderr or "")
    out = out.strip()

    # grep returns 1 when it finds nothing — that should NOT be a 500
    if result.returncode == 1 or not out:
        return {"output": "No such game process!"}

    # If ps/grep actually failed (missing binary, bad flags, etc.)
    if result.returncode != 0:
        return JSONResponse(
            {"error": "probe command failed", "output": out[:4000]},
            status_code=200,  # keep it non-500 for the lab
        )

    return {"output": out[:4000]}