"""
Deterministic ATS (Applicant Tracking System) scoring engine.

Produces a blended ATS score from two components:
  - Structural score  (section presence, length, keyword density)  — 40 %
  - LLM-supplied score (holistic quality judgement)                — 60 %

Also provides JD (job-description) keyword matching for /resume/score-jd.
"""
import re
from app.services.skill_extractor import normalize_skill, _alias_to_canonical

# ── ATS section weights ───────────────────────────────────────────────────────
# Each section contributes to the structural score when present.
_SECTION_WEIGHTS: dict[str, int] = {
    "education": 15,
    "skills": 20,
    "projects": 20,
    "experience": 15,
    "certifications": 10,
    "summary": 10,
    "objective": 5,
    "achievements": 5,
}

# Bonus keywords that boost keyword density score
_IMPACT_VERBS = {
    "developed", "built", "designed", "implemented", "created", "led",
    "improved", "optimized", "deployed", "automated", "managed", "delivered",
    "architected", "integrated", "researched", "analysed", "analyzed",
    "reduced", "increased", "achieved", "collaborated", "mentored",
}

# Penalized filler phrases that hurt ATS scores in real systems
_FILLER_PHRASES = {
    "hard worker", "team player", "fast learner", "go-getter",
    "think outside the box", "detail-oriented", "passionate about",
    "responsible for", "duties included",
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _word_tokens(text: str) -> list[str]:
    """Return lowercase word tokens from text."""
    return re.findall(r"\b[a-z][a-z0-9+#.-]*\b", text.lower())


def _section_score(sections_found: list[str]) -> int:
    """
    Score 0-100 based on which sections are present in the resume.
    Uses _SECTION_WEIGHTS; caps at 100.
    """
    total = sum(_SECTION_WEIGHTS.get(s, 0) for s in sections_found)
    return min(100, total)


def _keyword_density_score(text: str) -> int:
    """
    Score 0-100 based on:
    - Presence of impact verbs (+2 per unique verb, max 40)
    - Absence of filler phrases (-5 per phrase, floor 0)
    - Known technical skill keyword count (+3 per unique match, max 60)
    """
    lower = text.lower()
    words = set(_word_tokens(text))

    # Impact verb score (max 40)
    verb_hits = len(_IMPACT_VERBS & words)
    verb_score = min(40, verb_hits * 2)

    # Filler penalty
    filler_penalty = sum(5 for phrase in _FILLER_PHRASES if phrase in lower)

    # Technical skill keyword score (max 60)
    skill_hits = sum(1 for alias in _alias_to_canonical if alias in lower)
    skill_score = min(60, skill_hits * 3)

    raw = verb_score + skill_score - filler_penalty
    return max(0, min(100, raw))


def _length_score(text: str) -> int:
    """
    Score 0-100 based on resume length (word count).
    Ideal range: 300-700 words.  Under 150 or over 1200 loses points.
    """
    wc = len(text.split())
    if wc < 150:
        return 20
    elif wc < 300:
        return 50
    elif wc <= 700:
        return 100
    elif wc <= 1200:
        return 80
    else:
        return 60  # over-stuffed


def compute_structural_score(text: str, sections_found: list[str]) -> int:
    """
    Compute the deterministic structural ATS sub-score (0-100).
    Weighted blend of section presence, keyword density, and length.
    """
    sec = _section_score(sections_found)
    kw = _keyword_density_score(text)
    ln = _length_score(text)
    # Weights: sections 40%, keywords 40%, length 20%
    return round(sec * 0.40 + kw * 0.40 + ln * 0.20)


def blend_ats_score(llm_score: int | float | None, structural_score: int) -> int:
    """
    Blend the LLM-supplied score (60%) with the deterministic structural
    score (40%).  If llm_score is missing or out of range, fall back to
    structural_score only.
    """
    if llm_score is None or not isinstance(llm_score, (int, float)):
        return structural_score
    llm_score = max(0, min(100, float(llm_score)))
    blended = round(llm_score * 0.60 + structural_score * 0.40)
    return max(0, min(100, blended))


# ── JD keyword matching ───────────────────────────────────────────────────────

def score_against_jd(resume_text: str, resume_skills: list[str], jd_text: str) -> dict:
    """
    Deterministically compare a resume against a job description (JD) by:
    1. Extracting all skill aliases mentioned in the JD.
    2. Normalizing them to canonical form.
    3. Checking overlap with the student's resume skills.

    Returns a dict with:
        matched_skills   – skills in both JD and resume
        missing_skills   – skills in JD but not in resume
        match_pct        – overlap percentage (0-100)
        jd_keyword_count – total unique skills found in JD
    """
    if not jd_text or not jd_text.strip():
        return {
            "matched_skills": [],
            "missing_skills": [],
            "match_pct": 0,
            "jd_keyword_count": 0,
            "error": "Job description text is empty.",
        }

    jd_lower = jd_text.lower()
    # Find all canonical skills mentioned anywhere in the JD
    jd_skills: set[str] = set()
    for alias, canonical in _alias_to_canonical.items():
        # Match whole word/token (avoid partial matches like "c" inside "cache")
        if re.search(r"\b" + re.escape(alias) + r"\b", jd_lower):
            jd_skills.add(canonical)

    if not jd_skills:
        return {
            "matched_skills": [],
            "missing_skills": [],
            "match_pct": 0,
            "jd_keyword_count": 0,
            "error": "No recognizable technical skills found in the job description.",
        }

    # Normalize resume skills to canonical set
    resume_canonical: set[str] = {normalize_skill(s) for s in resume_skills}

    matched = sorted(jd_skills & resume_canonical)
    missing = sorted(jd_skills - resume_canonical)
    match_pct = round(len(matched) / len(jd_skills) * 100) if jd_skills else 0

    return {
        "matched_skills": matched,
        "missing_skills": missing,
        "match_pct": match_pct,
        "jd_keyword_count": len(jd_skills),
    }
