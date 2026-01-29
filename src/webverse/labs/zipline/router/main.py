from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, PlainTextResponse
import httpx

app = Starlette()

HOST_MAP = {
    "zipline.local": "http://public:8000",
    "internal-api.zipline.local": "http://internal-api:9000",
}

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _host_only(host_header: str) -> str:
    return (host_header or "").split(":")[0].strip().lower()


@app.route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy(request: Request) -> Response:
    host = _host_only(request.headers.get("host", ""))
    upstream = HOST_MAP.get(host)
    if not upstream:
        return PlainTextResponse("Unknown host", status_code=404)

    url = f"{upstream}{request.url.path}"
    if request.url.query:
        url += f"?{request.url.query}"

    headers = {}
    for k, v in request.headers.items():
        lk = k.lower()
        if lk in HOP_BY_HOP or lk == "host" or lk == "content-length":
            continue
        headers[k] = v

    body = await request.body()

    async with httpx.AsyncClient(follow_redirects=False, timeout=30.0) as client:
        r = await client.request(
            method=request.method,
            url=url,
            headers=headers,
            content=body,
        )

    resp_headers = {}
    for k, v in r.headers.items():
        lk = k.lower()
        if lk in HOP_BY_HOP or lk == "content-length":
            continue
        resp_headers[k] = v

    return Response(content=r.content, status_code=r.status_code, headers=resp_headers, media_type=r.headers.get("content-type"))
