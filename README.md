# AssessmentForge

**An MCP Server for Standards-Aligned State Assessment Item Generation**

Generate high-quality practice assessment items aligned to every U.S. state's standardized tests — powered by per-state `.md` skill guides and the Model Context Protocol.

---

## Coverage

| Component | Count | Status |
|-----------|-------|--------|
| **States + DC** | 51 | All Tier 1 (complete) |
| **Skill Guides** | 153 | 3 per state (ELA, MATH, SCI) |
| **Registry Entries** | 51 | Full blueprints, item types, rubrics, templates, standards |

### Assessment Frameworks

| Framework | States |
|-----------|--------|
| **SBAC (Smarter Balanced)** | CA, WA, OR, ID, HI, NV, MT, SD, ND, VT, NH, ME, CT, DE |
| **PARCC-derived** | IL, NJ, MD, CO, RI, NM, DC |
| **Custom/State-specific** | TX, NY, FL, OH, PA, GA, MA, MI, NC, VA, IN, MN, TN, LA, MS, KY, AL, AR, SC, WI, WV, AZ, UT, WY, KS, NE, OK, MO, IA, AK |

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

| Tool | Description | Example Use |
|:-----|:------------|:------------|
| `list_states` | List all states with tier and subject info | "What states are available?" |
| `list_available_skill_guides` | Show which guides exist for a state | "What guides does Ohio have?" |
| `get_skill_guide` | Retrieve specific sections from a guide | "Show me the OH ELA scoring rubrics" |
| `get_state_blueprint` | Get blueprint/claims structure | "What's the blueprint for CA MATH?" |
| `get_item_types` | List item types for a state + subject | "What item types does TX ELA use?" |
| `get_scoring_rubric` | Get rubric for a specific item type | "Show me the PA TDA rubric" |
| `get_generation_templates` | Get fill-in item templates | "Get MATH templates for NY" |
| `list_standards` | List standards by grade | "What are the Grade 5 ELA standards for FL?" |
| `generate_items` | Assemble full generation context | "Generate a Grade 7 ELA item for CA" |
| `generate_practice_set` | Assemble a complete mini-assessment | "Create a 10-item Grade 8 MATH set for IL" |

---

## How to Use It

### Generating Assessment Items

The primary workflow uses `generate_items` or `generate_practice_set`. These tools assemble a **context bundle** containing:

- **Generation prompt** — fully specified instructions for item creation
- **Skill guide context** — relevant sections from the state's markdown guide
- **Rubric** — scoring criteria for the requested item type
- **Template** — a fill-in template matching the request
- **Quality checklist** — verification criteria

The calling LLM uses this bundle to generate standards-aligned items.

**Example prompts:**

```
Generate 5 Grade 6 ELA items for Ohio that assess reading informational text at DOK 2-3.

Create a Grade 8 MATH practice set for California covering Claims 1 and 2.

Generate a Grade 5 Science constructed response item for Illinois about ecosystem interactions.

Write a Grade 4 ELA selected-response item for Texas aligned to TEKS.ELA4.6A.
```

### Browsing State Information

To understand a state's assessment before generating items:

```
1. get_state_blueprint("OH", "ELA")       → Claims, weightings, DOK distribution
2. get_item_types("OH", "ELA")            → Item types used on the test
3. get_scoring_rubric("OH", "ELA", "ER")  → Extended response rubric
4. get_skill_guide("OH", "ELA", ["Contextualization"])  → Ohio-specific topics
```

### Comparing States

```
1. get_state_blueprint("CA", "MATH")  → SBAC 4-claim structure
2. get_state_blueprint("TX", "MATH")  → TEKS-based reporting categories
3. get_item_types("CA", "ELA")        → SBAC item types (SR, EBSR, PT-FW...)
4. get_item_types("PA", "ELA")        → PSSA item types (MC, SA, TDA...)
```

---

## Skill Guide Schema

Every `.md` guide follows a 12-section structure:

| # | Section | Content | When to Reference |
|---|---------|---------|-------------------|
| 1 | **Overview** | Assessment metadata, performance levels | Starting point for any state |
| 2 | **Standards Framework** | Key standards by grade band | Aligning items to standards |
| 3 | **Test Structure** | Sessions, timing, item counts | Understanding test format |
| 4 | **Claims & Blueprint** | Weightings, DOK distribution | Balancing a practice set |
| 5 | **Item Types & Formats** | Each type with examples | Writing specific item types |
| 6 | **DOK / Cognitive Complexity** | DOK levels with examples | Setting cognitive demand |
| 7 | **Subject-Specific** | ELA: Text Complexity / MATH: Math Practices / SCI: 3D Design | Subject-specific guidance |
| 8 | **Scoring Rubrics** | Rubric tables for CR items | Scoring constructed responses |
| 9 | **Item Generation Templates** | Fill-in templates with placeholders | Starting point for item writing |
| 10 | **Contextualization** | State-specific topics and phenomena | Making items locally relevant |
| 11 | **Quality Checklist** | Verification checklist + pitfalls | Pre-flight review |
| 12 | **Prompt Patterns** | Request-to-recipe mappings | Quick-start item generation |

---

## Project Structure

```
stateassessmentsmcp/
├── server/
│   ├── __init__.py
│   └── main.py              ← MCP server (FastMCP): tools, models, caching
├── skills/
│   ├── state_registry.json  ← Structured metadata for all 51 entries
│   ├── _shared/             ← Cross-state frameworks (CCSS-ELA, CCSS-Math, NGSS)
│   ├── CA/                  ← California
│   │   ├── CA-ELA.md
│   │   ├── CA-MATH.md
│   │   └── CA-SCI.md
│   ├── TX/                  ← Texas
│   │   └── ...
│   └── {STATE}/             ← ... all 51 states/DC follow this pattern
├── tests/
├── Dockerfile
├── requirements.txt
└── README.md
```

## Registry Schema

Each entry in `state_registry.json`:

```json
{
  "name": "State Name",
  "tier": 1,
  "grades": ["3","4","5","6","7","8","11"],
  "assessments": { "ELA": "...", "MATH": "...", "SCI": "..." },
  "standards_framework": { "ELA": "...", "MATH": "...", "SCI": "..." },
  "testing_window": "April – May",
  "vendor": "...",
  "subjects": ["ELA", "MATH", "SCI"],
  "blueprints": { "ELA": {...}, "MATH": {...}, "SCI": {...} },
  "item_types": { "ELA": [...], "MATH": [...], "SCI": [...] },
  "rubrics": { "ELA": {...}, "MATH": {...}, "SCI": {...} },
  "generation_templates": { "ELA": [...], "MATH": [...], "SCI": [...] },
  "standards": { "ELA": {...}, "MATH": {...}, "SCI": {...} }
}
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_TRANSPORT` | `stdio` | `stdio` (Claude Desktop) or `http` (remote) |
| `MCP_HOST` | `0.0.0.0` | HTTP bind host |
| `MCP_PORT` | `8000` | HTTP port |

## Docker

```bash
docker build -t assessmentforge .
docker run -p 8000:8000 assessmentforge
```

Connect your MCP client to `http://localhost:8000/mcp`.

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

## License

MIT
