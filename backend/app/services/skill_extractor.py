import json
import os
import re
from rapidfuzz import process, fuzz
from app.services.llm import ask_llm_json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_MASTER_PATH = os.path.join(BASE_DIR, "data", "skills_master.json")

# ── Load at import time ────────────────────────────────────────────────────────
with open(SKILLS_MASTER_PATH, "r", encoding="utf-8") as f:
    skills_master: dict[str, list[str]] = json.load(f)

# Build a flat alias → canonical lookup for O(1) exact matches
_alias_to_canonical: dict[str, str] = {}
for canonical, aliases in skills_master.items():
    _alias_to_canonical[canonical.lower()] = canonical
    for alias in aliases:
        _alias_to_canonical[alias.lower().strip()] = canonical

# Build a flat list of all known aliases for rapidfuzz batch lookup
_all_aliases: list[str] = list(_alias_to_canonical.keys())

# ── Internal helpers ───────────────────────────────────────────────────────────

def _clean(skill: str) -> str:
    """Lowercase, strip, collapse whitespace, remove surrounding punctuation."""
    skill = skill.strip().lower()
    skill = re.sub(r"[^\w\s.#+/-]", "", skill)   # keep common tech chars
    skill = re.sub(r"\s+", " ", skill)
    return skill


def _safe_str_list(value) -> list[str]:
    """Coerce any value to a flat list of non-empty strings."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if v and str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _safe_projects(value) -> list[dict]:
    """
    Coerce the LLM 'projects' field to a list of valid project dicts.
    Handles: list[dict], list[str], None, dict.
    """
    if not value:
        return []
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []

    cleaned = []
    for item in value:
        if isinstance(item, str):
            cleaned.append({"name": item, "tech": [], "description": item})
        elif isinstance(item, dict):
            cleaned.append({
                "name": str(item.get("name") or item.get("title") or "Untitled").strip(),
                "tech": _safe_str_list(item.get("tech") or item.get("technologies") or item.get("stack") or []),
                "description": str(item.get("description") or item.get("desc") or "").strip(),
            })
    return cleaned


def _validate_llm_output(raw: dict) -> dict:
    """
    Sanitize and coerce every field from the LLM response into expected types.
    Returns a clean dict with guaranteed keys and types — never raises.
    """
    skills = _safe_str_list(raw.get("skills") or raw.get("skill_list") or [])
    projects = _safe_projects(raw.get("projects") or raw.get("project_list") or [])
    education = _safe_str_list(raw.get("education") or raw.get("education_list") or [])
    certifications = _safe_str_list(
        raw.get("certifications") or raw.get("certification_list") or raw.get("certs") or []
    )
    suggestions = _safe_str_list(
        raw.get("suggestions") or raw.get("improvement_suggestions") or raw.get("tips") or []
    )

    # ATS score: expect 0-100 number, reject strings/nulls
    raw_score = raw.get("ats_score") or raw.get("score") or raw.get("ats") or 0
    try:
        ats_score = float(raw_score)
        if not (0 <= ats_score <= 100):
            ats_score = 0.0
    except (TypeError, ValueError):
        ats_score = 0.0

    return {
        "skills": skills,
        "projects": projects,
        "education": education,
        "certifications": certifications,
        "ats_score": ats_score,
        "suggestions": suggestions,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def normalize_skill(skill_name: str) -> str:
    """
    Return the canonical skill name for a raw skill string.

    Strategy (in order of priority):
    1. Exact alias match (case-insensitive) → instant return.
    2. Fuzzy match against all aliases using WRatio ≥ 82 → canonical.
    3. Fall back to title-cased original so the user still sees the skill.
    """
    if not skill_name or not skill_name.strip():
        return skill_name

    cleaned = _clean(skill_name)

    # 1. Exact match
    if cleaned in _alias_to_canonical:
        return _alias_to_canonical[cleaned]

    # 2. Fuzzy match – search against all known aliases
    match = process.extractOne(cleaned, _all_aliases, scorer=fuzz.WRatio)
    if match and match[1] >= 82:
        return _alias_to_canonical[match[0]]

    # 3. Graceful fallback
    return skill_name.strip().title()


def normalize_skills_list(raw_skills: list[str]) -> list[str]:
    """Normalize a list of raw skill strings and deduplicate."""
    seen: set[str] = set()
    result: list[str] = []
    for s in raw_skills:
        canonical = normalize_skill(s)
        if canonical and canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return result


def analyze_resume(raw_text: str) -> dict:
    """
    Send resume text to the LLM, extract structured data, validate/sanitize
    every field, normalize skills, and blend the ATS score with the
    deterministic structural score.

    Returns a dict with keys:
        skills, projects, education, certifications, ats_score, suggestions
    Never raises — errors are returned as {"error": "..."}.
    """
    # Import here to avoid circular dependency at module load
    from app.services.resume_parser import detect_sections
    from app.services.ats_engine import compute_structural_score, blend_ats_score

    prompt = f"""
    Analyze the following resume text. Extract skills, projects, education, and certifications.
    Calculate an ATS score (0-100) based on standard industry criteria such as:
    - Presence of key sections (education, skills, experience, projects)
    - Use of action verbs and quantifiable achievements
    - Technical keyword density
    - Clarity and length

    Return EXACTLY this JSON structure with no extra keys:
    {{
      "skills": ["skill1", "skill2"],
      "projects": [{{"name": "Project Name", "tech": ["tech1", "tech2"], "description": "what it does"}}],
      "education": ["B.E. Computer Science, XYZ University, 2024"],
      "certifications": ["AWS Certified Cloud Practitioner"],
      "ats_score": 72,
      "suggestions": ["Add quantifiable metrics to your experience", "Include a professional summary section"]
    }}

    Important rules:
    - "skills" must be a flat array of strings only
    - "projects" must be an array of objects with name/tech/description
    - "ats_score" must be an integer between 0 and 100
    - "suggestions" must be specific, actionable improvement tips (3-5 items)
    - If a section is not found, return an empty array []

    Resume Text:
    {raw_text[:4000]}
    """

    result = ask_llm_json(prompt, retries=2)

    if "error" in result:
        return result

    # Validate and coerce all fields
    clean = _validate_llm_output(result)

    # Normalize skills through Phase 2.1 pipeline
    clean["skills"] = normalize_skills_list(clean["skills"])

    # Compute deterministic structural score and blend with LLM score
    sections_found = detect_sections(raw_text)
    structural = compute_structural_score(raw_text, sections_found)
    clean["ats_score"] = blend_ats_score(clean["ats_score"], structural)

    # Expose structural breakdown for transparency (optional, non-breaking)
    clean["ats_breakdown"] = {
        "structural_score": structural,
        "sections_detected": sections_found,
    }

    return clean