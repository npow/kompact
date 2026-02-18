"""Synthetic fixture generators for benchmark scenarios.

Six large scenarios with seeded randomness for reproducibility.
Each generator returns a ScenarioFixture with messages, needles, and metadata.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field

from kompact.types import ContentBlock, ContentType, Message, Role


@dataclass
class ScenarioFixture:
    """A benchmark scenario with messages and expected needles."""

    name: str
    description: str
    messages: list[Message]
    needles: list[str]
    content_breakdown: dict[str, int] = field(default_factory=dict)


def _rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


# ---------------------------------------------------------------------------
# 1. Search-heavy: 100 JSON search results
# ---------------------------------------------------------------------------

def search_heavy() -> ScenarioFixture:
    """~50K chars of JSON search results with needles embedded."""
    r = _rng(42)

    domains = [
        "example.com", "docs.python.org", "stackoverflow.com",
        "github.com", "developer.mozilla.org", "medium.com",
        "reddit.com", "news.ycombinator.com", "arxiv.org", "wikipedia.org",
    ]
    topics = [
        "machine learning", "database optimization", "REST API design",
        "kubernetes deployment", "CI/CD pipeline", "authentication",
        "caching strategies", "load balancing", "microservices",
        "event-driven architecture", "GraphQL", "WebSocket",
    ]

    results = []
    for i in range(100):
        topic = r.choice(topics)
        domain = r.choice(domains)
        results.append({
            "id": i,
            "title": f"{topic.title()} - Best Practices and Implementation Guide Part {i}",
            "url": f"https://{domain}/articles/{topic.replace(' ', '-')}-{i}",
            "snippet": f"This comprehensive guide covers {topic} including setup, "
                       f"configuration, performance tuning, and troubleshooting. "
                       f"Updated for 2024 with the latest best practices. "
                       f"Keywords: {', '.join(r.sample(topics, 3))}.",
            "score": round(r.uniform(0.1, 0.99), 3),
            "published": f"2024-{r.randint(1,12):02d}-{r.randint(1,28):02d}",
            "author": f"Author{r.randint(1, 50)}",
            "word_count": r.randint(500, 5000),
            "category": r.choice(["tutorial", "reference", "blog", "paper", "documentation"]),
            "language": "en",
        })

    # Insert needles
    needle1 = "CRITICAL: The API rate limit is 1000 requests per minute per API key"
    needle2 = "BUG-7823: Memory leak in connection pooler when using TLS 1.3"
    needle3 = "Deploy branch feature/auth-v2 to staging by Friday EOD"

    results[17]["snippet"] = needle1
    results[63]["snippet"] = needle2
    results[89]["snippet"] = needle3

    json_text = json.dumps(results, indent=2)
    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text="Search for articles about system design"),
        ]),
        Message(role=Role.ASSISTANT, content=[
            ContentBlock(
                type=ContentType.TOOL_USE,
                text="",
                tool_use_id="search_1",
                tool_name="web_search",
            ),
        ]),
        Message(role=Role.USER, content=[
            ContentBlock(
                type=ContentType.TOOL_RESULT,
                text=json_text,
                tool_use_id="search_1",
            ),
        ]),
    ]

    return ScenarioFixture(
        name="search_heavy",
        description="100 JSON search results (~50K chars). Tests TOON + JSON Crusher.",
        messages=messages,
        needles=[needle1, needle2, needle3],
        content_breakdown={"json_array": len(json_text)},
    )


# ---------------------------------------------------------------------------
# 2. Code-heavy: 4 Python files
# ---------------------------------------------------------------------------

def code_heavy() -> ScenarioFixture:
    """~40K chars of Python code with needles in comments/strings."""
    r = _rng(43)

    def _gen_python_file(name: str, num_classes: int, num_funcs: int) -> str:
        lines = [
            f'"""Module {name} — auto-generated for benchmarking."""',
            "",
            "from __future__ import annotations",
            "",
            "import os",
            "import json",
            "import logging",
            "from dataclasses import dataclass, field",
            "from typing import Any, Optional",
            "",
            f'logger = logging.getLogger("{name}")',
            "",
        ]

        for ci in range(num_classes):
            cname = f"{''.join(w.title() for w in r.sample(['data', 'config', 'service', 'handler', 'manager', 'processor', 'client', 'factory', 'builder', 'validator'], 2))}{ci}"
            lines.append("@dataclass")
            lines.append(f"class {cname}:")
            lines.append(f'    """Class {cname} handles {r.choice(["data processing", "request handling", "config management", "state tracking"])}."""')
            lines.append("")

            for ai in range(r.randint(3, 6)):
                atype = r.choice(["str", "int", "float", "bool", "list[str]", "dict[str, Any]", "Optional[str]"])
                lines.append(f"    attr_{ai}: {atype} = {_default_for_type(atype)}")
            lines.append("")

            for fi in range(r.randint(2, 4)):
                fname = f"{'_'.join(r.sample(['get', 'set', 'update', 'delete', 'process', 'validate', 'transform', 'fetch', 'compute', 'handle'], 2))}_{fi}"
                params = ", ".join(
                    f"{p}: {r.choice(['str', 'int', 'Any'])}"
                    for p in r.sample(["value", "key", "data", "options", "context"], r.randint(1, 3))
                )
                ret = r.choice(["str", "int", "bool", "dict[str, Any]", "list[str]", "None"])
                lines.append(f"    def {fname}(self, {params}) -> {ret}:")
                lines.append(f'        """Perform {fname.replace("_", " ")} operation."""')
                # Body
                for _ in range(r.randint(5, 15)):
                    lines.append(f"        {_random_statement(r)}")
                lines.append("")
            lines.append("")

        for fi in range(num_funcs):
            fname = f"module_func_{fi}"
            lines.append(f"def {fname}(input_data: Any) -> Any:")
            lines.append(f'    """Process input_data through {fname}."""')
            for _ in range(r.randint(8, 20)):
                lines.append(f"    {_random_statement(r)}")
            lines.append("")

        return "\n".join(lines)

    files = {
        "models.py": _gen_python_file("models", 4, 3),
        "services.py": _gen_python_file("services", 3, 5),
        "handlers.py": _gen_python_file("handlers", 3, 4),
        "utils.py": _gen_python_file("utils", 2, 8),
    }

    needle1 = 'SQL_INJECTION_VULN = "Fix SQL injection in user_query parameter"'
    needle2 = 'RACE_CONDITION_WORKAROUND = "Temporary workaround for race condition in cache invalidation"'
    needle3 = "API_SECRET_KEY = 'sk-prod-98765-do-not-commit'"

    # Insert needles as module-level assignments in files that won't be
    # masked by observation_masker (keep_last_n=3, so only models.py is masked)
    files["services.py"] = files["services.py"].replace(
        "import json", f"import json\n\n{needle1}"
    )
    files["handlers.py"] += f"\n{needle2}\n"
    files["utils.py"] += f"\n{needle3}\n"

    messages = []
    for fname, content in files.items():
        messages.extend([
            Message(role=Role.ASSISTANT, content=[
                ContentBlock(
                    type=ContentType.TOOL_USE,
                    text="",
                    tool_use_id=f"read_{fname}",
                    tool_name="read_file",
                ),
            ]),
            Message(role=Role.USER, content=[
                ContentBlock(
                    type=ContentType.TOOL_RESULT,
                    text=content,
                    tool_use_id=f"read_{fname}",
                ),
            ]),
        ])

    total_chars = sum(len(c) for c in files.values())
    return ScenarioFixture(
        name="code_heavy",
        description=f"4 Python files (~{total_chars // 1000}K chars). Tests Code Compressor.",
        messages=messages,
        needles=[needle1, needle2, needle3],
        content_breakdown={f: len(c) for f, c in files.items()},
    )


def _default_for_type(t: str) -> str:
    if t == "str":
        return '""'
    if t == "int":
        return "0"
    if t == "float":
        return "0.0"
    if t == "bool":
        return "False"
    if t.startswith("list"):
        return "field(default_factory=list)"
    if t.startswith("dict"):
        return "field(default_factory=dict)"
    if t.startswith("Optional"):
        return "None"
    return "None"


def _random_statement(r: random.Random) -> str:
    stmts = [
        'result = {}',
        'logger.info("Processing step")',
        'if value is None:\n            raise ValueError("value required")',
        'data = json.loads(json.dumps(value))',
        'items = [x for x in range(10) if x > 0]',
        'output = {k: v for k, v in data.items()}',
        'assert len(result) > 0, "empty result"',
        'return result',
        'temp = os.environ.get("TEMP_DIR", "/tmp")',
        'count += 1',
        'buffer.append(item)',
        'status = "ok" if valid else "error"',
        'for item in collection:\n            processed.append(item)',
        'try:\n            result = process(data)\n        except Exception as e:\n            logger.error(f"Failed: {e}")',
    ]
    return r.choice(stmts)


# ---------------------------------------------------------------------------
# 3. Log-heavy: 500-line server log
# ---------------------------------------------------------------------------

def log_heavy() -> ScenarioFixture:
    """~50K chars of server logs with repeated patterns and needles."""
    r = _rng(44)

    endpoints = ["/api/v1/users", "/api/v1/orders", "/api/v1/products",
                 "/api/v1/auth", "/api/v1/search", "/health", "/metrics"]
    methods = ["GET", "POST", "PUT", "DELETE"]
    status_codes = [200, 200, 200, 200, 200, 201, 204, 301, 400, 404, 500]

    lines = []
    for i in range(500):
        hour = r.randint(0, 23)
        minute = r.randint(0, 59)
        second = r.randint(0, 59)
        ms = r.randint(0, 999)
        ts = f"2024-01-15T{hour:02d}:{minute:02d}:{second:02d}.{ms:03d}Z"

        endpoint = r.choice(endpoints)
        method = r.choice(methods)
        status = r.choice(status_codes)
        duration = r.randint(1, 500)
        level = "ERROR" if status >= 500 else "WARN" if status >= 400 else "INFO"

        lines.append(
            f"[{ts}] {level} server.http - {method} {endpoint} "
            f"status={status} duration={duration}ms "
            f"request_id=req-{r.randint(10000,99999)} "
            f"user_id=user-{r.randint(1,1000)}"
        )

        # Add occasional multi-line entries
        if status == 500 and r.random() < 0.3:
            lines.append(f"[{ts}] ERROR server.http - Traceback (most recent call last):")
            lines.append(f'  File "/app/handlers.py", line {r.randint(10,200)}, in handle_request')
            lines.append(f"    result = process(request)")
            lines.append(f"  File \"/app/services.py\", line {r.randint(10,200)}, in process")
            lines.append(f"    raise RuntimeError(\"internal error\")")
            lines.append(f"RuntimeError: internal error")

    # Insert needles
    needle1 = "[2024-01-15T12:00:00.000Z] CRITICAL server.main - DATABASE CONNECTION POOL EXHAUSTED: max_connections=100 active=100 waiting=47"
    needle2 = "[2024-01-15T14:30:00.000Z] ERROR security.auth - BRUTE FORCE DETECTED: 500 failed login attempts from IP 192.168.1.100 in 60s"
    needle3 = "[2024-01-15T16:45:00.000Z] WARN billing.stripe - PAYMENT PROCESSING DELAYED: Stripe API latency >5000ms, queue depth=234"

    lines.insert(150, needle1)
    lines.insert(350, needle2)
    lines.insert(450, needle3)

    log_text = "\n".join(lines)
    messages = [
        Message(role=Role.ASSISTANT, content=[
            ContentBlock(
                type=ContentType.TOOL_USE,
                text="",
                tool_use_id="logs_1",
                tool_name="get_server_logs",
            ),
        ]),
        Message(role=Role.USER, content=[
            ContentBlock(
                type=ContentType.TOOL_RESULT,
                text=log_text,
                tool_use_id="logs_1",
            ),
        ]),
    ]

    return ScenarioFixture(
        name="log_heavy",
        description=f"500+ line server log (~{len(log_text) // 1000}K chars). Tests Log Compressor.",
        messages=messages,
        needles=[needle1, needle2, needle3],
        content_breakdown={"log_output": len(log_text)},
    )


# ---------------------------------------------------------------------------
# 4. Schema-heavy: 60 tool definitions + short conversation
# ---------------------------------------------------------------------------

def schema_heavy() -> ScenarioFixture:
    """~80K chars: 60 tool definitions with a short conversation."""
    r = _rng(45)

    categories = ["file", "search", "git", "terminal", "browser", "database",
                   "docker", "kubernetes", "aws", "gcp", "test", "lint"]

    tools_json = []
    for i in range(60):
        cat = r.choice(categories)
        tool_name = f"{cat}_{r.choice(['read', 'write', 'list', 'delete', 'search', 'create', 'update', 'deploy', 'run', 'check'])}_{i}"
        num_params = r.randint(2, 8)
        params = {}
        required = []
        for pi in range(num_params):
            pname = f"param_{pi}"
            ptype = r.choice(["string", "integer", "boolean", "array", "object"])
            params[pname] = {
                "type": ptype,
                "description": f"The {pname} parameter for {tool_name}. "
                               f"This controls the {r.choice(['input', 'output', 'filter', 'format', 'scope', 'target'])} "
                               f"of the operation. Must be a valid {ptype}.",
            }
            if pi < 2:
                required.append(pname)
        tools_json.append({
            "name": tool_name,
            "description": f"Tool {tool_name} — performs {cat} operations. "
                           f"Use this tool when you need to {r.choice(['read', 'write', 'modify', 'search', 'analyze'])} "
                           f"{cat}-related resources in the workspace. "
                           f"This tool supports batch operations and returns structured results.",
            "input_schema": {
                "type": "object",
                "properties": params,
                "required": required,
            },
        })

    schema_text = json.dumps(tools_json, indent=2)

    # Short conversation
    needle1 = "Use the database_search_42 tool to find all orders with status=failed from last 24h"
    needle2 = "IMPORTANT: The kubernetes cluster k8s-prod-east is running out of memory on node pool workers-high-mem"
    needle3 = "SECRET: The database migration password is 'migrate-2024-q4-prod'"

    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text=f"Available tools:\n{schema_text}"),
        ]),
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text=needle1),
        ]),
        Message(role=Role.ASSISTANT, content=[
            ContentBlock(type=ContentType.TEXT, text="I'll search the database for failed orders."),
            ContentBlock(
                type=ContentType.TOOL_USE,
                text="",
                tool_use_id="db_1",
                tool_name="database_search_42",
            ),
        ]),
        Message(role=Role.USER, content=[
            ContentBlock(
                type=ContentType.TOOL_RESULT,
                text=json.dumps([{"order_id": f"ord-{i}", "status": "failed",
                                  "amount": r.randint(10, 1000), "reason": "payment_declined"}
                                 for i in range(20)], indent=2),
                tool_use_id="db_1",
            ),
        ]),
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text=needle2),
        ]),
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text=needle3),
        ]),
    ]

    return ScenarioFixture(
        name="schema_heavy",
        description=f"60 tool definitions + conversation (~{len(schema_text) // 1000}K chars). Tests Schema Optimizer.",
        messages=messages,
        needles=[needle1, needle2, needle3],
        content_breakdown={"tool_schemas": len(schema_text), "conversation": 500},
    )


# ---------------------------------------------------------------------------
# 5. Conversation-heavy: 25 turns with tool calls
# ---------------------------------------------------------------------------

def conversation_heavy() -> ScenarioFixture:
    """~60K chars: 25 turns with 8 tool call/result pairs."""
    r = _rng(46)

    messages: list[Message] = []

    # System-like first message
    messages.append(Message(role=Role.USER, content=[
        ContentBlock(type=ContentType.TEXT,
                     text="You are a software engineering assistant. Help me debug and fix issues in the codebase."),
    ]))

    tool_results_data = [
        ("read_file", json.dumps({"content": _gen_python_file_short(r), "path": "/app/main.py"}, indent=2)),
        ("search_code", json.dumps([{"file": f"/app/{f}.py", "line": r.randint(1, 100),
                                     "match": f"def process_{f}(data):", "context": "..." * 50}
                                    for f in ["auth", "billing", "users", "orders", "search"]], indent=2)),
        ("run_tests", "\n".join([f"{'PASS' if r.random() > 0.2 else 'FAIL'} test_{i} ({r.randint(1,500)}ms)"
                                 for i in range(50)])),
        ("git_diff", "\n".join([f"{'+'if r.random()>0.5 else '-'} {_random_statement(r)}"
                                for _ in range(80)])),
        ("read_file", json.dumps({"content": _gen_python_file_short(r), "path": "/app/services.py"}, indent=2)),
        ("list_files", json.dumps([f"/app/{d}/{f}.py" for d in ["models", "views", "services", "utils"]
                                   for f in ["__init__", "base", "helpers", r.choice(["auth", "cache", "db"])]], indent=2)),
        ("run_command", f"$ npm run build\n" + "\n".join([f"  Building module {i}/25..." for i in range(25)]) + "\nBuild complete in 4.2s"),
        ("search_code", json.dumps([{"file": f"/app/tests/test_{f}.py", "line": r.randint(1, 50),
                                     "match": f"def test_{f}_integration():", "context": "..." * 30}
                                    for f in ["auth", "billing", "users"]], indent=2)),
    ]

    user_messages = [
        "Can you read the main application file?",
        "Search for all process functions in the codebase",
        "Run the test suite and show me the results",
        "Show me the git diff for recent changes",
        "Now read the services file",
        "List all Python files in the project",
        "Run the build command",
        "Search for integration tests",
    ]

    assistant_responses = [
        "Let me read that file for you.",
        "I'll search for process functions across the codebase.",
        "Running the test suite now.",
        "Here's the recent git diff.",
        "Reading the services file.",
        "Listing all Python files.",
        "Running the build.",
        "Searching for integration tests.",
    ]

    # Build conversation with interleaved tool calls
    for i, (tool_name, tool_output) in enumerate(tool_results_data):
        if i < len(user_messages):
            messages.append(Message(role=Role.USER, content=[
                ContentBlock(type=ContentType.TEXT, text=user_messages[i]),
            ]))

        messages.append(Message(role=Role.ASSISTANT, content=[
            ContentBlock(type=ContentType.TEXT, text=assistant_responses[min(i, len(assistant_responses) - 1)]),
            ContentBlock(
                type=ContentType.TOOL_USE,
                text="",
                tool_use_id=f"call_{i}",
                tool_name=tool_name,
            ),
        ]))

        messages.append(Message(role=Role.USER, content=[
            ContentBlock(
                type=ContentType.TOOL_RESULT,
                text=tool_output,
                tool_use_id=f"call_{i}",
            ),
        ]))

    # Add some more user/assistant exchanges
    for i in range(5):
        messages.append(Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT,
                         text=f"Follow-up question {i}: Can you explain how the {r.choice(['auth', 'billing', 'caching'])} module works?"),
        ]))
        messages.append(Message(role=Role.ASSISTANT, content=[
            ContentBlock(type=ContentType.TEXT,
                         text=f"The module works by {' '.join(r.choices(['processing', 'validating', 'transforming', 'caching', 'routing', 'filtering'], k=20))} the data through several stages..." * 3),
        ]))

    # Insert needles in different positions
    needle1 = "URGENT: Production database replication lag is 45 seconds and increasing"
    needle2 = "The root cause is in /app/services.py line 42: connection pool timeout set to 1ms instead of 1000ms"
    needle3 = "Deploy hotfix branch fix/db-pool-timeout to production ASAP — approved by @oncall-lead"

    messages.insert(8, Message(role=Role.USER, content=[
        ContentBlock(type=ContentType.TEXT, text=needle1),
    ]))
    messages.insert(16, Message(role=Role.USER, content=[
        ContentBlock(type=ContentType.TEXT, text=needle2),
    ]))
    messages.append(Message(role=Role.USER, content=[
        ContentBlock(type=ContentType.TEXT, text=needle3),
    ]))

    total_chars = sum(len(b.text) for m in messages for b in m.content)
    return ScenarioFixture(
        name="conversation_heavy",
        description=f"25 turns, 8 tool calls (~{total_chars // 1000}K chars). Tests Observation Masker.",
        messages=messages,
        needles=[needle1, needle2, needle3],
        content_breakdown={"tool_results": total_chars // 2, "conversation": total_chars // 2},
    )


def _gen_python_file_short(r: random.Random) -> str:
    lines = [
        "from __future__ import annotations",
        "import logging",
        "",
        'logger = logging.getLogger(__name__)',
        "",
    ]
    for i in range(r.randint(5, 10)):
        lines.append(f"def func_{i}(data: dict) -> dict:")
        lines.append(f'    """Process data through func_{i}."""')
        for _ in range(r.randint(5, 15)):
            lines.append(f"    {_random_statement(r)}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 6. Mixed-realistic: everything combined
# ---------------------------------------------------------------------------

def mixed_realistic() -> ScenarioFixture:
    """~100K chars: system prompt + tools + code + JSON + logs combined."""
    r = _rng(47)

    # System prompt
    system_text = (
        "You are Claude, an AI assistant made by Anthropic. You have access to a variety of tools "
        "for file operations, code search, terminal commands, and web browsing. Always think step by "
        "step. When debugging, start by reading the relevant code, then form a hypothesis, then test it.\n\n"
        "Current workspace: /Users/developer/project-alpha\n"
        f"Session ID: {r.randint(100000, 999999)}\n"
        "Date: 2024-01-15\n"
    )

    # Tool definitions (15 tools)
    tools_text = json.dumps([{
        "name": f"tool_{i}",
        "description": f"Tool {i} for {'|'.join(r.sample(['files', 'search', 'git', 'terminal', 'browser'], 2))} operations. " * 3,
        "input_schema": {
            "type": "object",
            "properties": {f"p{j}": {"type": "string", "description": f"Parameter {j}"} for j in range(r.randint(2, 5))},
        },
    } for i in range(15)], indent=2)

    # Code content
    code_text = _gen_python_file_short(r) + "\n" + _gen_python_file_short(r)

    # JSON search results
    search_results = json.dumps([{
        "id": i, "title": f"Result {i}", "url": f"https://example.com/{i}",
        "score": round(r.uniform(0.1, 0.99), 3),
        "snippet": f"Content for result {i} with various details..." * 3,
    } for i in range(50)], indent=2)

    # Log output
    log_lines = []
    for i in range(200):
        ts = f"2024-01-15T{r.randint(0,23):02d}:{r.randint(0,59):02d}:{r.randint(0,59):02d}Z"
        level = r.choice(["INFO", "INFO", "INFO", "DEBUG", "WARN", "ERROR"])
        log_lines.append(f"[{ts}] {level} app.main - Processing request {r.randint(1000,9999)}")
    log_text = "\n".join(log_lines)

    needle1 = "CRITICAL BUG: User data is being written to unencrypted S3 bucket s3://prod-user-data-raw"
    needle2 = "The fix requires updating /app/storage.py to use s3://prod-user-data-encrypted with KMS key arn:aws:kms:us-east-1:123456789:key/abc-def"
    needle3 = "Performance regression: p99 latency increased from 200ms to 1.5s after commit abc123f"

    messages = [
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text=f"System context:\n{system_text}\n\nAvailable tools:\n{tools_text}"),
        ]),
        Message(role=Role.ASSISTANT, content=[
            ContentBlock(type=ContentType.TEXT, text="I'll start by examining the codebase."),
            ContentBlock(type=ContentType.TOOL_USE, text="", tool_use_id="t1", tool_name="read_file"),
        ]),
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TOOL_RESULT, text=code_text, tool_use_id="t1"),
        ]),
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text=needle1),
        ]),
        Message(role=Role.ASSISTANT, content=[
            ContentBlock(type=ContentType.TEXT, text="Let me search for more context."),
            ContentBlock(type=ContentType.TOOL_USE, text="", tool_use_id="t2", tool_name="search_code"),
        ]),
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TOOL_RESULT, text=search_results, tool_use_id="t2"),
        ]),
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text=needle2),
        ]),
        Message(role=Role.ASSISTANT, content=[
            ContentBlock(type=ContentType.TEXT, text="Checking the logs for more details."),
            ContentBlock(type=ContentType.TOOL_USE, text="", tool_use_id="t3", tool_name="get_logs"),
        ]),
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TOOL_RESULT, text=log_text, tool_use_id="t3"),
        ]),
        Message(role=Role.USER, content=[
            ContentBlock(type=ContentType.TEXT, text=needle3),
        ]),
    ]

    total_chars = sum(len(b.text) for m in messages for b in m.content)
    return ScenarioFixture(
        name="mixed_realistic",
        description=f"System prompt + tools + code + JSON + logs (~{total_chars // 1000}K chars). Tests all transforms.",
        messages=messages,
        needles=[needle1, needle2, needle3],
        content_breakdown={
            "system_and_tools": len(system_text) + len(tools_text),
            "code": len(code_text),
            "search_json": len(search_results),
            "logs": len(log_text),
        },
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_GENERATORS = [
    search_heavy,
    code_heavy,
    log_heavy,
    schema_heavy,
    conversation_heavy,
    mixed_realistic,
]


def generate_all() -> list[ScenarioFixture]:
    """Generate all scenario fixtures."""
    return [gen() for gen in ALL_GENERATORS]
