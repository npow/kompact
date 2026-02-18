# System Design Document — Kompact

## Overview

Kompact is a multi-layer context optimization proxy. It intercepts HTTP requests to LLM providers, applies a pipeline of transforms to reduce token count, then forwards the optimized request.

## System Architecture

```
┌─────────────────────────────────────────────────┐
│                   Kompact Proxy                    │
│                                                  │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐ │
│  │  Parser   │→│ Transform │→│  Serializer   │ │
│  │ (detect   │  │ Pipeline  │  │ (rebuild     │ │
│  │  format)  │  │           │  │  request)    │ │
│  └──────────┘  └───────────┘  └──────────────┘ │
│                      │                           │
│              ┌───────┴────────┐                  │
│              │  Metrics       │                  │
│              │  Tracker       │                  │
│              └────────────────┘                  │
└─────────────────────────────────────────────────┘
```

## Component Design

### 1. Proxy Server (`proxy/server.py`)

FastAPI application with routes:
- `POST /v1/messages` — Anthropic Messages API
- `POST /v1/chat/completions` — OpenAI Chat Completions API
- `GET /dashboard` — Metrics dashboard
- `GET /health` — Health check

Flow:
1. Receive request
2. Parse into internal `Message` types
3. Run transform pipeline
4. Rebuild request in original format
5. Forward to upstream provider
6. Stream response back to client
7. Record metrics

### 2. Message Parser (`parser/messages.py`)

Converts between provider-specific formats and internal types:
- Anthropic: `messages` array with content blocks
- OpenAI: `messages` array with `content` string or array

### 3. Transform Pipeline (`transforms/pipeline.py`)

Orchestrates transforms in order:
1. Schema Optimizer (Layer 1)
2. TOON, JSON Crusher, Code Compressor, Log Compressor (Layer 2)
3. Observation Masker (Layer 3)
4. Cache Aligner (Layer 4)

Each transform: `(messages: list[Message], config: TransformConfig) → TransformResult`

### 4. Compression Store (`cache/store.py`)

Stores full content replaced by compression markers:
- Key: content hash
- Value: original content + metadata
- TTL: adaptive based on access patterns
- Retrieval: tool call or marker expansion

### 5. Metrics Tracker (`metrics/tracker.py`)

Tracks per-request and cumulative:
- Tokens before/after per transform
- Compression ratio
- Cache hit rates
- Transform latencies

## Data Flow

```
Request body (JSON)
  → Parse messages (provider-specific → internal types)
  → Count input tokens
  → Run Layer 1: Schema optimization
  → Run Layer 2: Content compression (TOON, JSON crush, code, logs)
  → Run Layer 3: Observation masking
  → Run Layer 4: Cache alignment
  → Count output tokens
  → Record metrics (input - output = savings)
  → Serialize back to provider format
  → Forward to upstream
  → Stream response back
```

## Key Design Decisions

1. **Pure function transforms**: No side effects, easy to test and compose
2. **Provider-agnostic internals**: Parse once, transform once, serialize per-provider
3. **Streaming passthrough**: Response streaming is not modified (v0.1)
4. **In-process store**: No external dependencies (Redis, etc.) for v0.1
5. **Additive pipeline**: Each transform operates on the output of the previous one
