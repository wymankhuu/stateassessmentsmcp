# Architectural Patterns — AssessmentForge

## 1. Registry + File Hybrid

Structured data and narrative content are split across two storage formats and always used together.

- **`skills/state_registry.json`** holds machine-readable structured data: blueprints, item types, rubric score-point arrays, generation template objects, and sample standards. Consumed directly as Python dicts.
- **`skills/{STATE}/{STATE}-{SUBJECT}.md`** holds rich narrative content: rules, examples, item templates, quality checklists, and prompt patterns. Consumed as raw markdown strings passed to the calling LLM as context.

Tools compose from both sources. Example: `get_state_blueprint` (`server/main.py:356-390`) reads `blueprint_data` from the registry dict **and** extracts the `## Claims & Blueprint` section from the markdown guide. `generate_items` (`server/main.py:564-670`) similarly pulls structured templates from the registry and narrative context sections from the `.md` file.

**Implication:** When adding a new state, both sources must be populated. Registry-only states (Tier 2) can answer structural queries but will fail any tool that calls `_load_guide()`.

---

## 2. Module-Level Lazy Cache

Two module-scope caches prevent repeated disk reads across tool calls within a server session.

```
server/main.py:27  _REGISTRY: dict | None = None
server/main.py:28  _GUIDE_CACHE: dict[str, str] = {}   # "CA-ELA" → markdown text
```

`_load_registry()` (`server/main.py:31-36`) populates `_REGISTRY` on first call and returns it on subsequent calls. `_load_guide()` (`server/main.py:39-50`) caches guides by their `"{STATE}-{SUBJECT}"` composite key.

**Implication:** The server process must restart to pick up edits to `.md` files or `state_registry.json`. There is no cache invalidation mechanism.

---

## 3. State+Subject Composite Key

The string `"{STATE}-{SUBJECT}"` (e.g., `"CA-ELA"`, `"TX-SCI"`) is the canonical identifier used consistently across:

- The guide cache dict key (`server/main.py:28`)
- The filesystem path: `skills/{STATE}/{STATE}-{SUBJECT}.md` (`server/main.py:43`)
- Guide construction in `_load_guide()` (`server/main.py:41`)

All inputs are normalized to uppercase at tool entry points (`server/main.py:369`, `server/main.py:419`). This key convention is the join point between the registry and the file system.

---

## 4. Section Extraction Pattern

`_extract_sections(text, wanted)` (`server/main.py:53-66`) parses skill guide markdown by scanning for `## ` headings and capturing everything under matched headings. Matching is substring-based and case-insensitive.

Tools use this to return only the sections relevant to a request rather than the full guide:

- `get_state_blueprint` extracts `["Claims & Blueprint", "Blueprint", "Test Blueprint"]`
- `get_scoring_rubric` extracts `["Scoring Rubrics", "Rubrics"]`
- `generate_items` extracts 10 sections: item types, DOK, Lexile, rubrics, templates, checklist, prompt patterns (`server/main.py:615-627`)

**Implication:** All skill guides must use `## ` (H2) for section headings. Subsections using `### ` are captured under their parent H2 section and are included when the parent is matched. Section titles in `.md` files must match the strings passed to `_extract_sections` — see `server/main.py:376-377`, `server/main.py:506-507` for the expected titles.

---

## 5. Context Bundle Assembly

`generate_items` (`server/main.py:564-670`) and `generate_practice_set` (`server/main.py:676-740`) do not call an external model. They assemble a structured dict containing:

- `generation_prompt` — a fully-specified prompt built by `_build_generation_prompt()` (`server/main.py:69-122`)
- `skill_guide_context` — extracted markdown sections
- `rubric` — extracted rubric section
- `template` — the best-matching template text from the registry
- `quality_checklist` — extracted checklist section

The calling LLM receives this bundle and executes the generation. This pattern keeps the MCP server stateless with respect to generation and puts all content decisions in the skill guides and registry.

---

## 6. Pydantic Return Models for Structured Tools

Tools that return structured data use Pydantic v2 models (`server/main.py:160-224`):

| Model | Used by | Key fields |
|-------|---------|------------|
| `StateInfo` | `list_states` | state_code, assessments, tier, guides_available |
| `SkillGuideSummary` | `list_available_skill_guides` | sections_present, word_count, guide_available |
| `Blueprint` | `get_state_blueprint` | claims (list[dict]), raw_blueprint_text |
| `Standard` | `list_standards` | code, description, domain, dok_typical |
| `ItemType` | `get_item_types` | abbreviation, points, machine_scored |
| `ScoringRubric` | `get_scoring_rubric` | score_points (list[dict]), raw_rubric_text |
| `GenerationTemplate` | `get_generation_templates` | template_text, placeholders |

Tools returning generation bundles (`generate_items`, `generate_practice_set`) return plain `dict` because their payloads combine structured and narrative content that doesn't fit a fixed schema.

---

## 7. Skill Guide 12-Section Schema

Every `{STATE}-{SUBJECT}.md` file follows a fixed 12-section structure (verified across CA, TX, NY, FL, IL guides):

```
## 1. Overview              → assessment metadata table + achievement levels
## 2. Standards Framework   → key standards by grade band (tables)
## 3. Test Structure        → sessions, timing, item counts (ASCII diagram + tables)
## 4. Claims & Blueprint    → domain weightings, DOK distribution
## 5. Item Types & Formats  → per-type description + example item
## 6. Depth of Knowledge    → DOK 1–3/4 with science/ELA/math examples
## 7. [Text Complexity /    → ELA: Lexile tables; Science: 3D design guide
       Three-Dimensional
       Design]
## 8. Scoring Rubrics       → rubric tables for CR/FW/SA items
## 9. Item Generation       → fill-in-the-blank templates with placeholder lists
       Templates
## 10. Contextualization    → state-specific context table + anchoring phenomena
## 11. Quality Checklist    → pre-generation checklist + common pitfalls table
## 12. Prompt Patterns      → 5–7 pattern recipes mapping request → generation approach
```

The section names used here must match the substrings passed to `_extract_sections()` in the tool implementations.

---

## 8. Transport Abstraction via Environment Variable

The server exposes two transports from a single entry point (`server/main.py:743-754`):

- `MCP_TRANSPORT=stdio` (default) → `mcp.run()` — used by Claude Desktop
- `MCP_TRANSPORT=http` → `mcp.run(transport="streamable-http", ...)` — used for Docker/remote

The Dockerfile hard-sets `ENV MCP_TRANSPORT=http`. No code changes are needed to switch modes; only the env var changes.

---

## 9. Graceful Degradation via FileNotFoundError

`_load_guide()` raises `FileNotFoundError` when a guide is missing. Tools that optionally use guides catch this and fall back to registry-only responses:

```
server/main.py:374-379   get_state_blueprint — catches FileNotFoundError, sets raw_text to warning string
server/main.py:504-509   get_scoring_rubric  — same pattern
```

Tools that require the guide (`generate_items`, `generate_practice_set`) let the error propagate to the MCP caller, which surfaces it as a tool error. This is intentional — generation without a guide is not meaningful.
