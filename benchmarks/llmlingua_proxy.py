"""Minimal LLMLingua-2 compression proxy for benchmarking.

Usage:
    python benchmarks/llmlingua_proxy.py --port 7880 --upstream http://localhost:9091
"""

from __future__ import annotations

import argparse
import json

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

app = FastAPI(title="LLMLingua-2 Proxy")

_compressor = None
_upstream: str = "http://localhost:9091"


def get_compressor():
    global _compressor
    if _compressor is None:
        from llmlingua import PromptCompressor
        _compressor = PromptCompressor(
            model_name="microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
            use_llmlingua2=True,
            device_map="cpu",
        )
    return _compressor


def compress_text(text: str) -> str:
    if len(text) < 50:
        return text
    try:
        compressor = get_compressor()
        result = compressor.compress_prompt(
            text,
            rate=0.5,
            force_tokens=["\n", "?", ".", "!", ":", "{", "}", "[", "]"],
        )
        return result["compressed_prompt"]
    except Exception:
        return text


def compress_messages(messages: list[dict]) -> list[dict]:
    compressed = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > 50:
            compressed.append({**msg, "content": compress_text(content)})
        elif isinstance(content, list):
            new_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text", "")
                    if len(text) > 50:
                        new_parts.append({**part, "text": compress_text(text)})
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


@app.get("/health")
async def health():
    return {"status": "ok", "compressor": "llmlingua-2"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7880)
    parser.add_argument("--upstream", type=str, default="http://localhost:9091")
    args = parser.parse_args()
    global _upstream
    _upstream = args.upstream
    # Warm up the model on startup
    print("Loading LLMLingua-2 model (this takes ~30s)...")
    get_compressor()
    print("Model loaded.")
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
