# AssessmentForge

**An MCP Server for Standards-Aligned State Assessment Item Generation**

Generate high-quality practice assessment items aligned to every U.S. state's standardized tests — powered by per-state `.md` skill guides and the Model Context Protocol.

---

## Quick Start

### Prerequisites

- Python 3.12+
- `pip`

### Install

```bash
cd stateassessmentsmcp
pip install -r requirements.txt
```

### Run Locally (stdio transport — for Claude Desktop)

```bash
python -m server.main
```

### Run as HTTP Server (for remote MCP clients)

```bash
MCP_TRANSPORT=http python -m server.main
# or
uvicorn server.main:mcp.app --host 0.0.0.0 --port 8000
```

### Connect from Claude Desktop

Copy `claude_desktop_config.json` contents into your Claude Desktop config at:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Update the `cwd` path to point to this directory, then restart Claude Desktop.

---

## Available Tools

| Tool | Description |
|:-----|:------------|
| `list_states` | List all supported states and their assessment names |
| `list_available_skill_guides` | Show which state×subject guides are ready |
| `get_skill_guide` | Return the full .md skill guide for a state + subject |
| `get_state_blueprint` | Return blueprint/claims/weightings for a state assessment |
| `list_standards` | List standards for a state + subject + grade |
| `get_item_types` | Return item types and formats for a state assessment |
| `get_scoring_rubric` | Return scoring rubrics for constructed-response items |
| `get_generation_templates` | Return pre-formatted item templates |
| `generate_items` | Assemble full context + generation prompt for practice items |
| `generate_practice_set` | Assemble a complete mini-assessment generation bundle |

---

## Project Structure

```
stateassessmentsmcp/
├── server/
│   ├── __init__.py
│   └── main.py              ← MCP server (FastMCP)
├── skills/
│   ├── state_registry.json  ← All 50 states + DC metadata
│   ├── _shared/             ← Cross-state frameworks (CCSS, NGSS)
│   ├── CA/                  ← California skill guides
│   │   ├── CA-ELA.md
│   │   ├── CA-MATH.md
│   │   └── CA-SCI.md
│   ├── TX/                  ← Texas skill guides
│   ├── NY/                  ← New York skill guides
│   ├── FL/                  ← Florida skill guides
│   └── IL/                  ← Illinois skill guides
├── tests/
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## Skill Guides

Each `.md` file is a self-contained instruction manual with 12 standardized sections:

1. **Overview** — Assessment name, vendor, grades, testing window
2. **Standards Framework** — Standards by grade and domain
3. **Test Structure** — Sessions, timing, calculator/reference policies
4. **Claims & Blueprint** — Subclaims, point weightings, content distribution
5. **Item Types & Formats** — Every item type with descriptions and points
6. **DOK / Cognitive Complexity** — DOK level distribution
7. **Text Complexity** — Lexile ranges, passage requirements
8. **Scoring Rubrics** — Rubric templates for CR items
9. **Item Generation Templates** — Pre-formatted templates with placeholders
10. **Contextualization** — State-specific context suggestions
11. **Quality Checklist** — Pre-flight verification
12. **Prompt Patterns** — Common request → generation recipe mappings

### Currently Available Guides (Tier 1)

| State | ELA | Math | Science |
|-------|-----|------|---------|
| CA (CAASPP / Smarter Balanced) | ✅ | ✅ | ✅ |
| TX (STAAR 2023) | ✅ | ✅ | ✅ |
| NY (NYS Grades 3–8) | ✅ | ✅ | ✅ |
| FL (FAST) | ✅ | ✅ | ✅ |
| IL (IAR / ISA) | ✅ | ✅ | ✅ |

Tier 2 states (registry metadata only, guides in progress): PA, OH, GA, NJ, MA, NC, WA, CO, AZ, MI + all remaining states

---

## Docker Deployment

```bash
docker build -t assessmentforge .
docker run -p 8000:8000 assessmentforge
```

Connect your MCP client to `http://localhost:8000/mcp`.

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

---

## License

MIT
