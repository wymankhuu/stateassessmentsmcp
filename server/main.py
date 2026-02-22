"""
AssessmentForge MCP Server
FastMCP-based server for generating state assessment items aligned to
real U.S. standardized tests.

Usage:
  stdio (Claude Desktop):  python -m server.main
  HTTP:                    MCP_TRANSPORT=http python -m server.main
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

# ─── Path resolution ──────────────────────────────────────────────────────────
SERVER_DIR    = Path(__file__).parent
PROJECT_ROOT  = SERVER_DIR.parent
SKILLS_DIR    = PROJECT_ROOT / "skills"
REGISTRY_PATH = SKILLS_DIR / "state_registry.json"

# ─── Module-level cache ───────────────────────────────────────────────────────
_REGISTRY: dict | None = None
_GUIDE_CACHE: dict[str, str] = {}   # "CA-ELA" → markdown text


def _load_registry() -> dict:
    global _REGISTRY
    if _REGISTRY is None:
        with REGISTRY_PATH.open(encoding="utf-8") as f:
            _REGISTRY = json.load(f)
    return _REGISTRY


def _load_guide(state: str, subject: str) -> str:
    """Return raw markdown for a skill guide. Raises FileNotFoundError if missing."""
    key = f"{state.upper()}-{subject.upper()}"
    if key not in _GUIDE_CACHE:
        path = SKILLS_DIR / state.upper() / f"{key}.md"
        if not path.exists():
            raise FileNotFoundError(
                f"No skill guide found for {state.upper()} {subject.upper()}. "
                f"Expected: {path}"
            )
        _GUIDE_CACHE[key] = path.read_text(encoding="utf-8")
    return _GUIDE_CACHE[key]


def _extract_sections(text: str, wanted: list[str]) -> str:
    """Extract named ## sections from markdown (case-insensitive matching)."""
    wanted_lower = {s.lower() for s in wanted}
    lines = text.splitlines(keepends=True)
    capturing = False
    result: list[str] = []
    for line in lines:
        if line.startswith("## ") or line.startswith("# "):
            title = line.lstrip("# ").strip().lower()
            # Match if any wanted section is contained in the title
            capturing = any(w in title for w in wanted_lower)
        if capturing:
            result.append(line)
    return "".join(result)


def _build_generation_prompt(
    state_code: str,
    assessment_name: str,
    subject: str,
    grade: str,
    standard_code: str,
    item_type: str,
    dok_level: int,
    count: int,
    template_text: str,
    passage_provided: Optional[str],
    additional_constraints: Optional[str],
) -> str:
    """Build a dense, instruction-complete prompt for item generation."""
    passage_block = (
        f"\n\n## Passage / Stimulus\n{passage_provided}"
        if passage_provided
        else (
            f"\n\n## Passage / Stimulus\n"
            f"Generate or select an appropriate passage matching this assessment's "
            f"Lexile requirements for Grade {grade}. Use the Text Complexity section "
            f"of the skill guide to determine the correct Lexile band."
        )
    )
    constraints_block = (
        f"\n\n## Additional Constraints\n{additional_constraints}"
        if additional_constraints
        else ""
    )
    return f"""## AssessmentForge Item Generation Request

**Assessment:** {assessment_name} ({state_code})
**Subject:** {subject}  |  **Grade:** {grade}
**Standard:** {standard_code}
**Item Type:** {item_type}  |  **DOK Level:** {dok_level}
**Count:** {count} item(s)

## Generation Template
{template_text}
{passage_block}
{constraints_block}

## Generation Instructions
Using the skill guide context provided alongside this prompt:
1. Generate {count} item(s) in the exact format specified by the template above.
2. Ensure each item assesses {standard_code} at DOK {dok_level}.
3. Match the {assessment_name} scoring conventions precisely.
4. Run the Quality Checklist (from the skill guide) before finalizing.
5. Output each item with:
   - Stem / prompt
   - Answer choices (if applicable, labeled A/B/C/D)
   - Correct answer or scoring rubric
   - Alignment note: Standard | Item Type | DOK level
"""


def _build_session_prompt(
    state_code: str,
    subject: str,
    grade: str,
    session_number: int,
    claims: list[dict],
    focus_standards: Optional[list[str]],
    target_minutes: int,
    include_passages: bool,
) -> dict:
    """Build a single session's generation directive."""
    total_items = max(10, target_minutes // 3)
    claim_distribution: dict[str, int] = {}
    for c in claims:
        name = c.get("name", "Unknown Claim")
        weight = c.get("weight_pct", round(100 / max(len(claims), 1)))
        claim_distribution[name] = max(1, round(total_items * weight / 100))

    return {
        "session_number": session_number,
        "label": f"Session {session_number}",
        "target_items": total_items,
        "claim_distribution": claim_distribution,
        "focus_standards": focus_standards or f"All assessed standards for {state_code} {subject} Grade {grade}",
        "include_passages": include_passages,
        "generation_directive": (
            f"Generate Session {session_number} of a {state_code} {subject} "
            f"Grade {grade} practice assessment. "
            f"Target approximately {total_items} items distributed as: {claim_distribution}. "
            "Use the full skill guide context to match item types, DOK levels, "
            "Lexile ranges, and rubrics exactly to the real assessment."
        ),
    }


# ─── Pydantic return models ───────────────────────────────────────────────────

class StateInfo(BaseModel):
    state_code: str
    state_name: str
    assessments: dict[str, str]
    grades: list[str]
    tier: int
    guides_available: list[str]


class SkillGuideSummary(BaseModel):
    state_code: str
    subject: str
    assessment_name: str
    grades: list[str]
    sections_present: list[str]
    word_count: int
    guide_available: bool


class Blueprint(BaseModel):
    state_code: str
    subject: str
    assessment_name: str
    claims: list[dict]
    total_points: int
    session_count: int
    notes: str
    raw_blueprint_text: str


class Standard(BaseModel):
    code: str
    description: str
    domain: str
    grade: str
    dok_typical: int


class ItemType(BaseModel):
    name: str
    abbreviation: str
    description: str
    points: int | str
    machine_scored: bool
    example_stem: Optional[str] = None


class ScoringRubric(BaseModel):
    item_type: str
    trait: str
    score_points: list[dict]
    raw_rubric_text: str


class GenerationTemplate(BaseModel):
    template_id: str
    item_type: str
    dok_level: int
    grade_band: str
    template_text: str
    placeholders: list[str]


# ─── FastMCP instance ─────────────────────────────────────────────────────────

mcp = FastMCP(
    "AssessmentForge",
    instructions=(
        "You are a state assessment item generation engine. "
        "When a teacher or educator requests practice items, use the tools "
        "to load the appropriate state skill guide and return a complete "
        "generation context. The skill guide contains exact item formats, "
        "rubrics, Lexile requirements, and templates from the real state test. "
        "Use generate_items to assemble a ready-to-execute generation prompt, "
        "or get_skill_guide to load the full context directly."
    ),
)


# ─── Tool 1: list_states ──────────────────────────────────────────────────────

@mcp.tool()
def list_states(tier: Optional[int] = None) -> list[StateInfo]:
    """
    List all supported U.S. states and their assessment programs.

    Args:
        tier: Filter by implementation tier.
              1 = complete skill guides available.
              2 = registry metadata only (guides in progress).
              None = all states.

    Returns:
        List of StateInfo objects describing each state's assessments.
    """
    registry = _load_registry()
    results = []
    for code, meta in registry["states"].items():
        if tier is not None and meta.get("tier", 2) != tier:
            continue
        # Check which .md files actually exist on disk
        available = [
            s for s in meta.get("subjects", [])
            if (SKILLS_DIR / code / f"{code}-{s}.md").exists()
        ]
        results.append(StateInfo(
            state_code=code,
            state_name=meta["name"],
            assessments=meta.get("assessments", {}),
            grades=meta.get("grades", []),
            tier=meta.get("tier", 2),
            guides_available=available,
        ))
    return results


# ─── Tool 2: list_available_skill_guides ──────────────────────────────────────

@mcp.tool()
def list_available_skill_guides(
    state_code: Optional[str] = None,
    subject: Optional[str] = None,
) -> list[SkillGuideSummary]:
    """
    Show which state × subject skill guides are fully authored and ready to use.

    Args:
        state_code: Two-letter state code to filter (e.g. "CA"). None = all states.
        subject:    "ELA", "MATH", or "SCI". None = all subjects.

    Returns:
        List of SkillGuideSummary objects for each available guide.
    """
    registry = _load_registry()
    results = []
    for code, meta in registry["states"].items():
        if state_code and code != state_code.upper():
            continue
        for subj in meta.get("subjects", []):
            if subject and subj != subject.upper():
                continue
            path = SKILLS_DIR / code / f"{code}-{subj}.md"
            if not path.exists():
                continue
            text = _load_guide(code, subj)
            sections = [
                line.lstrip("# ").strip()
                for line in text.splitlines()
                if line.startswith("## ")
            ]
            results.append(SkillGuideSummary(
                state_code=code,
                subject=subj,
                assessment_name=meta.get("assessments", {}).get(subj, ""),
                grades=meta.get("grades", []),
                sections_present=sections,
                word_count=len(text.split()),
                guide_available=True,
            ))
    return results


# ─── Tool 3: get_skill_guide ──────────────────────────────────────────────────

@mcp.tool()
def get_skill_guide(
    state_code: str,
    subject: str,
    sections: Optional[list[str]] = None,
) -> str:
    """
    Return the full skill guide markdown for a state + subject combination.
    This is the primary context-loading tool — pass the returned text as
    context to item generation prompts.

    Args:
        state_code: Two-letter state code (e.g. "CA", "TX", "NY").
        subject:    "ELA", "MATH", or "SCI".
        sections:   Optional list of section titles to extract, e.g.:
                    ["Item Types & Formats", "Scoring Rubrics"].
                    None = return the full guide.

    Returns:
        Full markdown text of the skill guide (or requested sections only).
    """
    text = _load_guide(state_code, subject)
    if sections:
        text = _extract_sections(text, sections)
    return text


# ─── Tool 4: get_state_blueprint ─────────────────────────────────────────────

@mcp.tool()
def get_state_blueprint(state_code: str, subject: str) -> Blueprint:
    """
    Return the assessment blueprint including claims, point weightings,
    session structure, and content distribution.

    Args:
        state_code: Two-letter state code.
        subject:    "ELA", "MATH", or "SCI".

    Returns:
        Blueprint object with structured claim data and raw markdown section.
    """
    registry = _load_registry()
    state_code = state_code.upper()
    subject = subject.upper()
    meta = registry["states"].get(state_code, {})
    blueprint_data = meta.get("blueprints", {}).get(subject, {})

    raw_text = ""
    try:
        guide_text = _load_guide(state_code, subject)
        raw_text = _extract_sections(guide_text, ["Claims & Blueprint", "Blueprint", "Test Blueprint"])
    except FileNotFoundError:
        raw_text = "Skill guide not yet available for this state/subject."

    return Blueprint(
        state_code=state_code,
        subject=subject,
        assessment_name=meta.get("assessments", {}).get(subject, ""),
        claims=blueprint_data.get("claims", []),
        total_points=blueprint_data.get("total_points", 0),
        session_count=blueprint_data.get("session_count", 0),
        notes=blueprint_data.get("notes", ""),
        raw_blueprint_text=raw_text,
    )


# ─── Tool 5: list_standards ───────────────────────────────────────────────────

@mcp.tool()
def list_standards(
    state_code: str,
    subject: str,
    grade: str,
    domain: Optional[str] = None,
) -> list[Standard]:
    """
    List commonly assessed standards for a state + subject + grade combination.

    Note: Returns a representative subset of high-frequency standards.
    For the complete standards framework, use get_skill_guide with
    sections=["Standards Framework"].

    Args:
        state_code: Two-letter state code.
        subject:    "ELA", "MATH", or "SCI".
        grade:      Grade as string: "3", "4", ... "8", "10", "11", "EOC".
        domain:     Optional domain filter (e.g. "Reading: Informational Text").

    Returns:
        List of Standard objects with code, description, domain, and typical DOK.
    """
    registry = _load_registry()
    state_code = state_code.upper()
    subject = subject.upper()
    standards_list = (
        registry["states"]
        .get(state_code, {})
        .get("standards", {})
        .get(subject, {})
        .get(grade, [])
    )
    if domain:
        standards_list = [
            s for s in standards_list
            if domain.lower() in s.get("domain", "").lower()
        ]
    return [Standard(**s) for s in standards_list]


# ─── Tool 6: get_item_types ───────────────────────────────────────────────────

@mcp.tool()
def get_item_types(
    state_code: str,
    subject: str,
    machine_scored_only: bool = False,
) -> list[ItemType]:
    """
    Return all item types used in a state's assessment with full format descriptions.

    Args:
        state_code:          Two-letter state code.
        subject:             "ELA", "MATH", or "SCI".
        machine_scored_only: If True, exclude constructed-response (human-scored) items.

    Returns:
        List of ItemType objects describing each format.
    """
    registry = _load_registry()
    state_code = state_code.upper()
    subject = subject.upper()
    item_types_data = (
        registry["states"]
        .get(state_code, {})
        .get("item_types", {})
        .get(subject, [])
    )
    items = [ItemType(**it) for it in item_types_data]
    if machine_scored_only:
        items = [it for it in items if it.machine_scored]
    return items


# ─── Tool 7: get_scoring_rubric ───────────────────────────────────────────────

@mcp.tool()
def get_scoring_rubric(
    state_code: str,
    subject: str,
    item_type: str,
) -> ScoringRubric:
    """
    Return the official scoring rubric for a specific item type.

    Args:
        state_code: Two-letter state code.
        subject:    "ELA", "MATH", or "SCI".
        item_type:  Item type abbreviation, e.g. "ECR", "SCR", "PT-FW",
                    "ER", "OR", "FW", "SA". Use get_item_types to see
                    available abbreviations for a state.

    Returns:
        ScoringRubric with structured score point descriptions and raw rubric text.
    """
    state_code = state_code.upper()
    subject = subject.upper()
    item_type_upper = item_type.upper()

    registry = _load_registry()
    rubric_data = (
        registry["states"]
        .get(state_code, {})
        .get("rubrics", {})
        .get(subject, {})
        .get(item_type_upper, {})
    )

    raw_text = ""
    try:
        guide_text = _load_guide(state_code, subject)
        raw_text = _extract_sections(guide_text, ["Scoring Rubrics", "Rubrics"])
    except FileNotFoundError:
        raw_text = "Skill guide not yet available for this state/subject."

    return ScoringRubric(
        item_type=item_type,
        trait=rubric_data.get("trait", "See raw rubric text below"),
        score_points=rubric_data.get("score_points", []),
        raw_rubric_text=raw_text,
    )


# ─── Tool 8: get_generation_templates ─────────────────────────────────────────

@mcp.tool()
def get_generation_templates(
    state_code: str,
    subject: str,
    item_type: Optional[str] = None,
    dok_level: Optional[int] = None,
    grade_band: Optional[str] = None,
) -> list[GenerationTemplate]:
    """
    Return pre-formatted item generation templates with placeholders.
    Use these as scaffolds when prompting for item generation.

    Args:
        state_code:  Two-letter state code.
        subject:     "ELA", "MATH", or "SCI".
        item_type:   Filter by item type abbreviation (e.g. "MCQ", "EBSR", "OR").
        dok_level:   Filter by DOK level (1, 2, or 3).
        grade_band:  Filter by grade band: "3-5", "6-8", "HS".

    Returns:
        List of GenerationTemplate objects with fill-in-the-blank templates.
    """
    registry = _load_registry()
    state_code = state_code.upper()
    subject = subject.upper()
    templates_data = (
        registry["states"]
        .get(state_code, {})
        .get("generation_templates", {})
        .get(subject, [])
    )
    templates = [GenerationTemplate(**t) for t in templates_data]
    if item_type:
        templates = [t for t in templates if t.item_type == item_type.upper()]
    if dok_level is not None:
        templates = [t for t in templates if t.dok_level == dok_level]
    if grade_band:
        templates = [t for t in templates if t.grade_band == grade_band]
    return templates


# ─── Tool 9: generate_items ───────────────────────────────────────────────────

@mcp.tool()
def generate_items(
    state_code: str,
    subject: str,
    grade: str,
    standard_code: str,
    item_type: str,
    dok_level: int,
    count: int = 1,
    passage_provided: Optional[str] = None,
    additional_constraints: Optional[str] = None,
) -> dict:
    """
    Assemble all context needed to generate state-aligned assessment items.
    Returns a structured bundle for the calling LLM to execute.

    This tool does NOT call an external model. It returns:
    - "generation_prompt":    A fully-specified prompt ready for item generation.
    - "skill_guide_context":  Relevant sections of the skill guide (8 sections).
    - "rubric":               Applicable scoring rubric section.
    - "template":             The best-matching item template.
    - "quality_checklist":    Pre-generation checklist from the guide.

    Args:
        state_code:              Two-letter state code (e.g. "TX", "CA").
        subject:                 "ELA", "MATH", or "SCI".
        grade:                   Grade as string (e.g. "5", "8").
        standard_code:           Target standard code
                                 (e.g. "CCSS.ELA-Literacy.RI.5.3",
                                  "TEKS.Math6.3A", "NGSS.MS-PS1-1").
        item_type:               Item type abbreviation
                                 (e.g. "EBSR", "MCQ", "SCR", "OR", "SA").
        dok_level:               Depth of Knowledge level: 1, 2, or 3.
        count:                   Number of items to generate (1–5).
        passage_provided:        Optional passage text to use as stimulus.
        additional_constraints:  Any extra constraints
                                 (e.g. "Lexile 850-1000", "no calculators").

    Returns:
        Dict with generation_prompt, skill_guide_context, rubric,
        template, and quality_checklist.
    """
    state_code = state_code.upper()
    subject = subject.upper()

    guide_text = _load_guide(state_code, subject)
    registry = _load_registry()
    meta = registry["states"].get(state_code, {})
    assessment_name = meta.get("assessments", {}).get(subject, f"{state_code} {subject} Assessment")

    # Extract the most useful sections for generation
    relevant_sections = [
        "Item Types",
        "DOK",
        "Cognitive Complexity",
        "Text Complexity",
        "Lexile",
        "Scoring Rubrics",
        "Item Generation Templates",
        "Contextualization",
        "Quality Checklist",
        "Prompt Patterns",
    ]
    context = _extract_sections(guide_text, relevant_sections)

    # Find best-matching template
    templates_data = meta.get("generation_templates", {}).get(subject, [])
    matching = [
        t for t in templates_data
        if t.get("item_type", "").upper() == item_type.upper()
        and t.get("dok_level") == dok_level
    ]
    if not matching:
        # Fall back to same item type regardless of DOK
        matching = [
            t for t in templates_data
            if t.get("item_type", "").upper() == item_type.upper()
        ]
    template_text = matching[0]["template_text"] if matching else (
        f"No template found for {item_type} DOK {dok_level}. "
        "Generate an item in the standard format for this assessment."
    )

    generation_prompt = _build_generation_prompt(
        state_code=state_code,
        assessment_name=assessment_name,
        subject=subject,
        grade=grade,
        standard_code=standard_code,
        item_type=item_type,
        dok_level=dok_level,
        count=count,
        template_text=template_text,
        passage_provided=passage_provided,
        additional_constraints=additional_constraints,
    )

    rubric_section = _extract_sections(guide_text, ["Scoring Rubrics", "Rubrics"])
    checklist = _extract_sections(guide_text, ["Quality Checklist", "Checklist"])

    return {
        "generation_prompt": generation_prompt,
        "skill_guide_context": context,
        "rubric": rubric_section,
        "template": template_text,
        "quality_checklist": checklist,
    }


# ─── Tool 10: generate_practice_set ──────────────────────────────────────────

@mcp.tool()
def generate_practice_set(
    state_code: str,
    subject: str,
    grade: str,
    focus_standards: Optional[list[str]] = None,
    session_count: int = 1,
    target_minutes_per_session: int = 45,
    include_passages: bool = True,
) -> dict:
    """
    Assemble a complete mini-assessment generation bundle modelled on the
    target state test. Returns session-by-session generation prompts for
    the calling LLM to execute sequentially.

    Args:
        state_code:                  Two-letter state code.
        subject:                     "ELA", "MATH", or "SCI".
        grade:                       Grade as string.
        focus_standards:             Optional list of specific standards to emphasize.
        session_count:               Number of test sessions (1–3).
        target_minutes_per_session:  Approximate minutes per session (default 45).
        include_passages:            For ELA: whether to include full passage texts.

    Returns:
        Dict with set_blueprint, session_prompts (list), assembly_instructions,
        and full_skill_guide_context.
    """
    state_code = state_code.upper()
    subject = subject.upper()

    guide_text = _load_guide(state_code, subject)
    registry = _load_registry()
    meta = registry["states"].get(state_code, {})
    blueprint_data = meta.get("blueprints", {}).get(subject, {})
    claims = blueprint_data.get("claims", [])
    assessment_name = meta.get("assessments", {}).get(subject, f"{state_code} {subject} Assessment")

    session_prompts = []
    for i in range(max(1, min(session_count, 3))):
        prompt = _build_session_prompt(
            state_code=state_code,
            subject=subject,
            grade=grade,
            session_number=i + 1,
            claims=claims,
            focus_standards=focus_standards,
            target_minutes=target_minutes_per_session,
            include_passages=include_passages,
        )
        session_prompts.append(prompt)

    assembly_instructions = (
        f"Generate each session below in sequence using the full skill guide context. "
        f"After generating all {len(session_prompts)} session(s), assemble them into "
        f"a single practice test document with a cover page showing: "
        f"Assessment: {assessment_name}, Grade {grade}, State: {state_code}. "
        f"Include an answer key / scoring guide at the end."
    )

    return {
        "set_blueprint": blueprint_data,
        "session_prompts": session_prompts,
        "assembly_instructions": assembly_instructions,
        "full_skill_guide_context": guide_text,
    }


# ─── Startup ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "http":
        mcp.run(
            transport="streamable-http",
            host=os.getenv("MCP_HOST", "0.0.0.0"),
            port=int(os.getenv("MCP_PORT", "8000")),
        )
    else:
        mcp.run()
