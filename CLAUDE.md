# AssessmentForge — CLAUDE.md

## What This Is

MCP server that exposes 10 tools for generating U.S. state standardized assessment items.
Given a state + subject + grade, the server loads skill guide markdown and registry JSON,
then returns a ready-to-execute generation context to the calling LLM. The LLM generates
the actual items; this server provides the spec and context.

## Tech Stack

- **Python 3.12** · **FastMCP** (`mcp[cli]>=1.0.0`) — MCP server framework
- **Pydantic v2** — typed return models for all 10 tools
- **Uvicorn + Starlette** — HTTP transport (optional; default is stdio)
- **Docker** — containerized HTTP deployment

## Key Directories

| Path | Purpose |
|------|---------|
| `server/main.py` | Entire server: helper functions, Pydantic models, 10 `@mcp.tool()` definitions |
| `skills/state_registry.json` | Structured metadata for all 50 states + DC (blueprints, item types, rubrics, templates, sample standards) |
| `skills/{STATE}/` | Markdown skill guides (`{STATE}-{SUBJECT}.md`) — rich narrative used as LLM generation context |
| `skills/_shared/` | Cross-state framework references: CCSS ELA/Math, NGSS |
| `claude_desktop_config.json` | Claude Desktop integration — update `cwd` before use |

## Skill Guide Coverage

**Tier 1** (complete `.md` guides): CA, TX, NY, FL, IL — each has ELA, MATH, SCI guides.
**Tier 2** (registry metadata only, guides in progress): all remaining states.

The server checks file existence at runtime; tier value is advisory only
(`server/main.py:263-265`).

## Essential Commands

```bash
pip install -r requirements.txt

# stdio — Claude Desktop
python -m server.main

# HTTP — remote MCP clients
MCP_TRANSPORT=http python -m server.main
uvicorn server.main:mcp.app --host 0.0.0.0 --port 8000

# Docker
docker build -t assessmentforge .
docker run -p 8000:8000 assessmentforge

# Tests
pip install pytest && pytest tests/ -v
```

## Environment Variables

| Variable | Default | Values |
|----------|---------|--------|
| `MCP_TRANSPORT` | `stdio` | `stdio` (Claude Desktop) or `http` (remote) |
| `MCP_HOST` | `0.0.0.0` | HTTP bind host |
| `MCP_PORT` | `8000` | HTTP port |

## Adding a New State (Tier 1)

1. Add entry to `skills/state_registry.json` following the existing state schema
   (blueprints, item_types, rubrics, generation_templates, standards keys required)
2. Create `skills/{STATE}/` directory with three `.md` guides following the
   12-section skill guide schema (see any existing Tier 1 guide for the template)
3. Set `"tier": 1` in the registry once all three guides are present

## Additional Documentation

| File | When to Check |
|------|--------------|
| [.claude/docs/architectural_patterns.md](.claude/docs/architectural_patterns.md) | Adding tools, modifying data loading, extending the registry schema, or adding new skill guides |
