"""
Phase 2.2 ATS & Resume Analysis Tests
Run from: backend/
  python -m app.tests.test_phase22
"""
import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.resume_parser import extract_text_from_pdf, detect_sections, _clean_text
from app.services.skill_extractor import (
    _validate_llm_output, _safe_str_list, _safe_projects, normalize_skills_list,
)
from app.services.ats_engine import (
    compute_structural_score, blend_ats_score, score_against_jd,
    _section_score, _keyword_density_score, _length_score,
)

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
_total = _passed = 0

def ok(desc: str, expr: bool, extra: str = ""):
    global _total, _passed
    _total += 1
    if expr:
        _passed += 1
        print(f"  {PASS}  {desc}")
    else:
        print(f"  {FAIL}  {desc}" + (f"\n       {extra}" if extra else ""))

def eq(desc: str, got, expected):
    global _total, _passed
    _total += 1
    expr = got == expected
    if expr:
        _passed += 1
        print(f"  {PASS}  {desc}")
    else:
        print(f"  {FAIL}  {desc}\n       got={got!r}  expected={expected!r}")


# ═══════════════════════════════════════════════════════════════
# Section 1 – resume_parser helpers
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 1: resume_parser helpers --")

# _clean_text
dirty = "Hello\x00World\n\n\n\nEnd"
cleaned = _clean_text(dirty)
ok("Null byte removed", "\x00" not in cleaned)
ok("Triple blank lines collapsed to double", "\n\n\n" not in cleaned)

# detect_sections
sample_resume = """
John Doe
EDUCATION
B.E. Computer Science, VTU, 2024
SKILLS
Python, React, SQL
PROJECTS
SmartHome IoT System - Used ESP32 and MQTT
CERTIFICATIONS
AWS Cloud Practitioner
"""
sections = detect_sections(sample_resume)
ok("'education' detected",       "education" in sections)
ok("'skills' detected",          "skills" in sections)
ok("'projects' detected",        "projects" in sections)
ok("'certifications' detected",  "certifications" in sections)
ok("'experience' NOT detected",  "experience" not in sections)

# extract_text_from_pdf: empty bytes
try:
    extract_text_from_pdf(b"")
    ok("Empty bytes raises ValueError", False)
except ValueError as e:
    ok("Empty bytes raises ValueError", True)

# extract_text_from_pdf: short/garbage bytes
try:
    extract_text_from_pdf(b"short pdf garbage content")
    ok("Corrupt PDF raises ValueError", False)
except ValueError as e:
    ok("Corrupt PDF raises ValueError", True)


# ═══════════════════════════════════════════════════════════════
# Section 2 – _validate_llm_output
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 2: LLM output validation --")

# Perfect input passes through cleanly
perfect = {
    "skills": ["Python", "React"],
    "projects": [{"name": "App", "tech": ["Python"], "description": "desc"}],
    "education": ["B.E. CSE"],
    "certifications": ["AWS"],
    "ats_score": 75,
    "suggestions": ["Add metrics"]
}
v = _validate_llm_output(perfect)
eq("Perfect input: skills preserved",       v["skills"],         ["Python", "React"])
eq("Perfect input: ats_score preserved",    v["ats_score"],      75.0)
eq("Perfect input: suggestions preserved",  v["suggestions"],    ["Add metrics"])

# skills as null → empty list
v_null = _validate_llm_output({"skills": None})
eq("Null skills → []", v_null["skills"], [])

# skills as string → single-item list
v_str = _validate_llm_output({"skills": "Python"})
eq("String skills → ['Python']", v_str["skills"], ["Python"])

# ats_score as string → coerced to float
v_strscr = _validate_llm_output({"ats_score": "82"})
eq("String ats_score '82' → 82.0", v_strscr["ats_score"], 82.0)

# ats_score out of range → 0
v_oob = _validate_llm_output({"ats_score": 999})
eq("Out-of-range ats_score 999 → 0", v_oob["ats_score"], 0.0)

# ats_score as non-numeric → 0
v_nan = _validate_llm_output({"ats_score": "excellent"})
eq("Non-numeric ats_score → 0.0", v_nan["ats_score"], 0.0)

# Missing keys → all defaults
v_empty = _validate_llm_output({})
eq("Empty dict: skills=[]",         v_empty["skills"],         [])
eq("Empty dict: projects=[]",       v_empty["projects"],       [])
eq("Empty dict: education=[]",      v_empty["education"],      [])
eq("Empty dict: certifications=[]", v_empty["certifications"], [])
eq("Empty dict: ats_score=0.0",     v_empty["ats_score"],      0.0)
eq("Empty dict: suggestions=[]",    v_empty["suggestions"],    [])

# Alternative key names
v_alt = _validate_llm_output({
    "skill_list": ["Go", "Rust"],
    "score": 68,
    "tips": ["Fix formatting"]
})
eq("Alt key 'skill_list' → skills",  v_alt["skills"],      ["Go", "Rust"])
eq("Alt key 'score' → ats_score",    v_alt["ats_score"],   68.0)
eq("Alt key 'tips' → suggestions",   v_alt["suggestions"], ["Fix formatting"])


# ═══════════════════════════════════════════════════════════════
# Section 3 – _safe_projects
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 3: _safe_projects coercion --")

# List of strings → wrapped as dicts
p_strs = _safe_projects(["Smart Home", "ML Model"])
ok("String project list: 2 items",        len(p_strs) == 2)
eq("String project name preserved",       p_strs[0]["name"], "Smart Home")

# Proper dict with alternative keys
p_alt = _safe_projects([{"title": "MyApp", "technologies": ["React"], "desc": "cool"}])
eq("Alt key 'title' → name",        p_alt[0]["name"], "MyApp")
eq("Alt key 'technologies' → tech", p_alt[0]["tech"], ["React"])
eq("Alt key 'desc' → description",  p_alt[0]["description"], "cool")

# None → empty list
eq("None projects → []", _safe_projects(None), [])

# Dict (not list) → wrapped
p_single = _safe_projects({"name": "Solo", "tech": [], "description": "x"})
eq("Single dict → wrapped in list", len(p_single), 1)


# ═══════════════════════════════════════════════════════════════
# Section 4 – ATS engine: sub-scores
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 4: ATS engine sub-scores --")

# _section_score
eq("Full sections → max score cap",   _section_score(["education","skills","projects","experience","certifications","summary"]), 90)
eq("No sections → 0",                 _section_score([]), 0)
eq("Only skills → 20",               _section_score(["skills"]), 20)

# _length_score
ok("50 words → 20",    _length_score("word " * 50) == 20)
ok("200 words → 50",   _length_score("word " * 200) == 50)
ok("400 words → 100",  _length_score("word " * 400) == 100)
ok("1500 words → 60",  _length_score("word " * 1500) == 60)

# _keyword_density_score: resume with known skills
rich_resume = """
Developed a machine learning model using Python and scikit-learn.
Built RESTful APIs with FastAPI and deployed using Docker on AWS.
Led a team and improved system performance by 30%.
"""
kw_score = _keyword_density_score(rich_resume)
ok("Rich resume keyword score > 30", kw_score > 30, f"got {kw_score}")

# Filler penalty
filler_resume = "I am a hard worker and team player who is passionate about technology."
filler_score = _keyword_density_score(filler_resume)
rich_score = _keyword_density_score(rich_resume)
ok("Rich > filler keyword score", rich_score > filler_score,
   f"rich={rich_score} filler={filler_score}")

# compute_structural_score
struct_score = compute_structural_score(sample_resume, sections)
ok("Structural score is 0-100",       0 <= struct_score <= 100, f"got {struct_score}")
ok("Structured resume scores > 40",   struct_score > 40, f"got {struct_score}")

# blend_ats_score
eq("Blend(80, 60) = 72",              blend_ats_score(80, 60), 72)
eq("Blend(None, 55) = 55 (fallback)", blend_ats_score(None, 55), 55)
eq("Blend(0, 100) = 40",             blend_ats_score(0, 100), 40)
ok("Blend clamps at 100",            blend_ats_score(100, 100) == 100)
ok("Blend clamps at 0",              blend_ats_score(0, 0) == 0)


# ═══════════════════════════════════════════════════════════════
# Section 5 – score_against_jd
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 5: score_against_jd --")

resume_skills = ["Python", "SQL", "Machine Learning", "React", "Git"]

jd_full = """
We are looking for a Data Scientist with strong Python skills,
experience with machine learning, deep understanding of SQL,
and familiarity with TensorFlow or PyTorch.
"""
result = score_against_jd("", resume_skills, jd_full)
ok("JD score returns dict",                      isinstance(result, dict))
ok("Has matched_skills",                         "matched_skills" in result)
ok("Has missing_skills",                         "missing_skills" in result)
ok("Has match_pct",                              "match_pct" in result)
ok("Has jd_keyword_count",                       "jd_keyword_count" in result)
ok("Python matched",                             "Python" in result["matched_skills"])
ok("SQL matched",                                "SQL" in result["matched_skills"])
ok("Machine Learning matched",                   "Machine Learning" in result["matched_skills"])
ok("Deep Learning in missing (not in resume)",   "Deep Learning" in result["missing_skills"])
ok("match_pct is 0-100",                         0 <= result["match_pct"] <= 100)
ok("match_pct > 0 (has matches)",                result["match_pct"] > 0)

# Empty JD
result_empty = score_against_jd("", resume_skills, "")
ok("Empty JD returns error",  "error" in result_empty)

# JD with no recognizable skills
result_no_skills = score_against_jd("", resume_skills, "We seek a motivated individual with good communication skills and a positive attitude.")
ok("No-skill JD returns error or 0 match", "error" in result_no_skills or result_no_skills["match_pct"] == 0)

# JD matching via aliases
jd_alias = "Need someone with reactjs, nodejs, github, and postgresql experience."
result_alias = score_against_jd("", ["React", "Node.js", "Git", "PostgreSQL"], jd_alias)
ok("Alias JD: React matched via 'reactjs'",    "React" in result_alias.get("matched_skills", []))
ok("Alias JD: Node.js matched via 'nodejs'",   "Node.js" in result_alias.get("matched_skills", []))
ok("Alias JD: Git matched via 'github'",        "Git" in result_alias.get("matched_skills", []))

# ═══════════════════════════════════════════════════════════════
# Section 6 – Full analyze_resume output structure (mock)
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 6: _validate_llm_output full output structure --")

# Simulate a full messy LLM response (the kinds of garbage it actually returns)
messy_llm = {
    "skills": ["Python", None, "", "  ", "JavaScript", 42],
    "projects": [
        {"name": "App", "tech": ["React"], "description": "My app"},
        "Side project - Django blog",          # string project
        {"title": "AltTitle", "desc": "Alt"},  # alternative keys
    ],
    "education": "B.E. CSE, VTU",              # string instead of list
    "certifications": None,
    "ats_score": "78",                          # string score
    "improvement_suggestions": ["Fix X", "Fix Y"],  # alternate key
}

v = _validate_llm_output(messy_llm)

# Skills: nulls, blanks, ints stripped
ok("Messy skills: None/blank/int stripped",   None not in v["skills"] and "" not in v["skills"])
ok("Messy skills: 'Python' kept",              "Python" in v["skills"])
ok("Messy skills: 'JavaScript' kept",          "JavaScript" in v["skills"])
ok("Messy skills: int 42 coerced to '42'",     "42" in v["skills"])

# Projects: string project wrapped, alt keys resolved
ok("Messy projects: 3 items",                  len(v["projects"]) == 3)
ok("Messy projects: dict project preserved",   v["projects"][0]["name"] == "App")
ok("Messy projects: string project wrapped",   v["projects"][1]["name"] == "Side project - Django blog")
ok("Messy projects: alt key 'title' → name",   v["projects"][2]["name"] == "AltTitle")

# Education: string coerced to list
eq("Messy education: string → list",           v["education"], ["B.E. CSE, VTU"])

# Certifications: None → []
eq("Messy certifications: None → []",          v["certifications"], [])

# ATS score: string → float
eq("Messy ats_score: '78' → 78.0",             v["ats_score"], 78.0)

# Suggestions: alt key resolved
eq("Messy suggestions: alt key resolved",      v["suggestions"], ["Fix X", "Fix Y"])

# normalize_skills_list on messy skill list (after str coercion)
raw_for_norm = [s for s in v["skills"] if isinstance(s, str) and s.strip()]
normed = normalize_skills_list(raw_for_norm)
ok("Normalized skills: no duplicates",         len(normed) == len(set(normed)))

# ═══════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*55}")
print(f"  RESULTS: {_passed}/{_total} passed", end="")
if _passed == _total:
    print("  All tests passed!")
else:
    print(f"  ({_total - _passed} FAILED)")
print("=" * 55)
sys.exit(0 if _passed == _total else 1)
