import os
import time
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

API_BASE = "/api/v1"

app = FastAPI(title="Tricky Tunnels", version="1.0.0")

DATA_DIR = os.getenv("DATA_DIR", "/data")
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)


def seeded_marker():
    marker = Path(DATA_DIR) / "boot.txt"
    if not marker.exists():
        marker.write_text(f"booted_at={int(time.time())}\n", encoding="utf-8")


@app.on_event("startup")
def on_startup():
    seeded_marker()


@app.get("/", response_class=HTMLResponse)
def root():
    # Realistic: a lightweight landing page that calls the API.
    # Users can find the API base path via View Source / Network tab.
    return f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Tricky Tunnels</title>
    <style>
      body {{ font-family: sans-serif; max-width: 820px; margin: 40px auto; }}
      code {{ background: #f3f3f3; padding: 2px 6px; border-radius: 4px; }}
      pre {{ background: #f7f7f7; padding: 12px; border-radius: 8px; overflow: auto; }}
    </style>
  </head>
  <body>
    <h1>Tricky Tunnels</h1>
    <p>Welcome to APIverse demo lab.</p>
    <p>Client is loading profile from <code>{API_BASE}/profile</code> …</p>

    <h3>Response</h3>
    <pre id="out">Loading…</pre>

    <script>
      fetch("{API_BASE}/profile")
        .then(r => r.json())
        .then(j => {{
          document.getElementById("out").textContent = JSON.stringify(j, null, 2);
        }})
        .catch(e => {{
          document.getElementById("out").textContent = "Error: " + e;
        }});
    </script>
  </body>
</html>
""".strip()


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    # Realistic: sites often disallow internal/admin paths here.
    # This gives a subtle breadcrumb that "internal" exists.
    return "\n".join(
        [
            "User-agent: *",
            "Disallow: /internal/",
            "Disallow: /api/",
            "",
        ]
    )


@app.get(f"{API_BASE}/health")
def health(response: Response):
    # Realistic: advertise an API description document via Link header
    # (useful breadcrumb for beginners; not too hand-holdy)
    response.headers["Link"] = '</openapi.json>; rel="service-desc"'
    return {"ok": True}


@app.get(f"{API_BASE}/profile")
def profile():
    return {
        "id": "u_1001",
        "username": "demo_user",
        "plan": "free",
        "note": "Nothing sensitive here. Check what else the app exposes.",
    }


# --- VULNERABILITY: Unauthenticated config leak (info disclosure) ---
@app.get("/internal/config")
def debug_config():
    # More believable as a leftover internal diagnostic endpoint
    leak = {
        "app": {
            "name": os.getenv("APP_NAME"),
            "env": os.getenv("APP_ENV"),
            "version": "1.0.0",
        },
        "secrets": {
            "jwt_secret": os.getenv("JWT_SECRET"),
            "flag": os.getenv("FLAG"),
        },
        "internal": {"admin_url": os.getenv("INTERNAL_ADMIN_URL")},
        "runtime": {"pid": os.getpid(), "cwd": os.getcwd()},
    }
    return JSONResponse(leak)
