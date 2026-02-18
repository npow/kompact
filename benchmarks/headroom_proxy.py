"""Headroom compression proxy for benchmarking.

Uses SmartCrusher (their recommended approach) with default production settings.
ToolCrusher is deprecated per Headroom docs.

Usage:
    python benchmarks/headroom_proxy.py --port 7879 --upstream http://localhost:8084
"""

from __future__ import annotations

import argparse
import json

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from headroom import SmartCrusher, SmartCrusherConfig

app = FastAPI(title="Headroom Proxy")

_crusher: SmartCrusher | None = None
_upstream: str = "http://localhost:8084"


def get_crusher() -> SmartCrusher:
    global _crusher
    if _crusher is None:
        # Use their recommended production defaults
        _crusher = SmartCrusher(SmartCrusherConfig(
            enabled=True,
            min_tokens_to_crush=200,  # their default (not 50)
            max_items_after_crush=15,  # their default
            variance_threshold=2.0,  # standard 2-sigma
        ))
    return _crusher


def compress_messages(messages: list[dict]) -> list[dict]:
    """Compress message content with Headroom SmartCrusher."""
    crusher = get_crusher()

    # Extract query from last user message (SmartCrusher uses this for relevance)
    query = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                query = content[:500]
                break

    compressed = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > 100:
            try:
                result = crusher.crush(content, query=query)
                if result.was_modified:
                    compressed.append({**msg, "content": result.compressed})
                else:
                    compressed.append(msg)
            except Exception:
                compressed.append(msg)
        elif isinstance(content, list):
            new_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text", "")
                    if len(text) > 100:
                        try:
                            result = crusher.crush(text, query=query)
                            if result.was_modified:
                                new_parts.append({**part, "text": result.compressed})
                            else:
                                new_parts.append(part)
                        except Exception:
                            new_parts.append(part)
                    else:
                        new_parts.append(part)
                else:
                    new_parts.append(part)
            compressed.append({**msg, "content": new_parts})
        else:
            compressed.append(msg)
    return compressed


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    body = await request.json()
    body["messages"] = compress_messages(body.get("messages", []))

    headers = {"content-type": "application/json"}
    for key in ("authorization",):
        val = request.headers.get(key)
        if val:
            headers[key] = val

    async with httpx.AsyncClient(timeout=300.0) as client:
        if body.get("stream", False):
            resp = await client.send(
                client.build_request("POST", f"{_upstream}/v1/chat/completions",
                                     json=body, headers=headers),
                stream=True,
            )

            async def stream():
                async for chunk in resp.aiter_bytes():
                    yield chunk
                await resp.aclose()
            return StreamingResponse(stream(), status_code=resp.status_code,
                                     headers=dict(resp.headers))
        else:
            resp = await client.post(f"{_upstream}/v1/chat/completions",
                                     json=body, headers=headers)
            return Response(content=resp.content, status_code=resp.status_code,
                            headers=dict(resp.headers))


@app.post("/v1/messages")
async def messages(request: Request) -> Response:
    body = await request.json()
    body["messages"] = compress_messages(body.get("messages", []))

    headers = {}
    for key in ("authorization", "x-api-key", "anthropic-version", "content-type"):
        val = request.headers.get(key)
        if val:
            headers[key] = val
    if "content-type" not in headers:
        headers["content-type"] = "application/json"

    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(f"{_upstream}/v1/messages",
                                 json=body, headers=headers)
        return Response(content=resp.content, status_code=resp.status_code,
                        headers=dict(resp.headers))


@app.get("/health")
async def health():
    return {"status": "ok", "compressor": "headroom-smartcrusher"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7879)
    parser.add_argument("--upstream", type=str, default="http://localhost:8084")
    args = parser.parse_args()
    global _upstream
    _upstream = args.upstream
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
