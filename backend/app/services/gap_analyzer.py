import json
import os
from rapidfuzz import fuzz
from app.services.llm import ask_llm_json
from app.services.skill_extractor import normalize_skill

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYLLABUS_PATH = os.path.join(BASE_DIR, "data", "syllabus.json")
ROLES_PATH = os.path.join(BASE_DIR, "data", "roles.json")

with open(SYLLABUS_PATH, "r", encoding="utf-8") as f:
    syllabus_db = json.load(f)
with open(ROLES_PATH, "r", encoding="utf-8") as f:
    roles_db = json.load(f)

# ── Internal helpers ───────────────────────────────────────────────────────────

def _skills_match(skill_a: str, skill_b: str, threshold: int = 88) -> bool:
    """
    Return True if two skill strings refer to the same skill.

    First normalizes both through the canonical lookup, then falls back
    to a fuzzy token-set-ratio comparison so that minor variations
    ("Node.js" vs "Node", "ReactJS" vs "React") still match.
    """
    norm_a = normalize_skill(skill_a)
    norm_b = normalize_skill(skill_b)
    if norm_a.lower() == norm_b.lower():
        return True
    score = fuzz.token_set_ratio(norm_a.lower(), norm_b.lower())
    return score >= threshold


def _skill_in_set(skill: str, skill_set: set[str]) -> bool:
    """Check if `skill` semantically matches any skill in `skill_set`."""
    for s in skill_set:
        if _skills_match(skill, s):
            return True
    return False


def _normalize_skill_set(raw_skills: list[str]) -> set[str]:
    """Normalize a list of skill strings into a deduplicated canonical set."""
    return {normalize_skill(s) for s in raw_skills}


# ── Public API ────────────────────────────────────────────────────────────────

def get_role_requirements(target_role: str) -> dict:
    """Return skill→weight dict for a target role (catalog or LLM-generated)."""
    # Direct match first
    if target_role in roles_db:
        return roles_db[target_role]

    # Case-insensitive match
    for role_key in roles_db:
        if role_key.lower() == target_role.lower():
            return roles_db[role_key]

    # Fuzzy match against catalog roles (catches slight typos)
    best_role, best_score = None, 0
    for role_key in roles_db:
        score = fuzz.token_set_ratio(role_key.lower(), target_role.lower())
        if score > best_score:
            best_score = score
            best_role = role_key
    if best_score >= 80 and best_role:
        return roles_db[best_role]

    # Dynamic LLM fallback for non-catalog roles
    prompt = f"""
    List the top 6 core technical skills required for the job role: "{target_role}".
    Assign an importance weight from 1 to 3 for each.
    Return ONLY a JSON dictionary where keys are skill names and values are weights (1-3).
    Example: {{"Python": 3, "SQL": 2}}
    """
    ai_role = ask_llm_json(prompt)
    if isinstance(ai_role, dict) and "error" not in ai_role and ai_role:
        return ai_role

    return {"General Aptitude": 2, "Problem Solving": 3, "Core Engineering": 2}


def analyze_skill_gap(branch: str, current_sem: int, target_role: str, resume_skills: list) -> dict:
    """
    Compute a skill-gap report comparing role requirements against
    VTU syllabus skills (up to current_sem) and resume skills.

    Matching is canonical + fuzzy so that alias variations are handled.
    """
    role_reqs = get_role_requirements(target_role)

    # Collect VTU syllabus skills for the branch up to current_sem
    vtu_raw: list[str] = []
    branch_data = syllabus_db.get(branch, {})
    for sem, subjects in branch_data.items():
        if int(sem) <= current_sem:
            for sub in subjects:
                vtu_raw.extend(sub.get("skills", []))
    vtu_skills = _normalize_skill_set(vtu_raw)

    # Normalize resume skills to canonical form
    resume_skills_norm = _normalize_skill_set(resume_skills)

    # Union of everything the student has
    all_have = vtu_skills | resume_skills_norm

    covered_by_syllabus, from_resume, missing = [], [], []
    total_weight = sum(role_reqs.values())
    earned_weight = 0

    for req_skill, weight in role_reqs.items():
        req_canonical = normalize_skill(req_skill)

        # Check if the student has this skill (canonical OR fuzzy)
        in_vtu = _skill_in_set(req_canonical, vtu_skills)
        in_resume = _skill_in_set(req_canonical, resume_skills_norm)

        if in_vtu or in_resume:
            earned_weight += weight
            if in_resume and not in_vtu:
                from_resume.append(req_canonical)
            else:
                covered_by_syllabus.append({
                    "skill": req_canonical,
                    "status": "revise and add to resume" if not in_resume else "covered"
                })
        else:
            missing.append({"skill": req_canonical, "status": "learn from scratch"})

    match_pct = round((earned_weight / total_weight) * 100) if total_weight > 0 else 0
    return {
        "target_role": target_role,
        "covered_by_syllabus": covered_by_syllabus,
        "from_resume": from_resume,
        "missing": missing,
        "skill_match_pct": match_pct
    }