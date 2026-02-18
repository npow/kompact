# Harness Engineering Learnings

Key takeaways from OpenAI's harness engineering blog applied to Kompact.

## 1. AGENTS.md as Table of Contents

Keep AGENTS.md short (~100 lines). It's a map, not a manual.
Point to docs/ for details. Agents should find what they need in 2 hops.

## 2. Progressive Disclosure

- Level 0: AGENTS.md — what is this, where is everything
- Level 1: docs/sdd.md — how it works
- Level 2: src/kompact/transforms/ — individual transform implementations
- Level 3: tests/ — exact behavior specifications

## 3. Strict Architectural Boundaries

Types → Config → Transforms → Pipeline → Proxy → CLI

No circular dependencies. Each layer only imports from layers below it.

## 4. Mechanical Enforcement

- All transforms implement the same interface: `Transform` protocol
- Type checker enforces `TransformResult` return type
- Pipeline validates transform ordering
- Tests verify no user message modification

## 5. Agent Legibility

- File names match concepts (toon.py = TOON transform)
- Each file has a module docstring explaining what it does and why
- Config has sensible defaults — works out of the box
- Error messages include remediation steps

## 6. Golden Principles

Encoded as code, not just docs:
1. Pure transforms: enforced by type signature (no self mutation)
2. No user message modification: tested in every transform test
3. Token tracking: `TransformResult.tokens_saved` is required field
4. Realistic fixtures: test data from real agentic sessions
