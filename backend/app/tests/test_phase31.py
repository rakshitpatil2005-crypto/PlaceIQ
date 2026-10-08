"""
Phase 3.1 Personalized Learning Roadmap Tests
Run from: backend/
  python -m app.tests.test_phase31
"""
import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.roadmap_generator import (
    generate_personalized_roadmap,
    _extract_skill_lists,
    _validate_roadmap_output,
    _deterministic_roadmap_fallback,
    _get_resources,
)
from app.services.gap_analyzer import analyze_skill_gap

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
# Section 1 – Skill Extraction & Weight-Based Prioritization
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 1: Skill Extraction & Weight Prioritization --")

sample_gap = {
    "target_role": "Backend Developer",
    "covered_by_syllabus": [
        {"skill": "Operating Systems", "status": "revise and add to resume"},
        {"skill": "Computer Networks", "status": "covered"},
        {"skill": "Data Structures", "status": "revise and add to resume"},
    ],
    "from_resume": ["Python"],
    "missing": [
        {"skill": "REST APIs", "status": "learn from scratch"},
        {"skill": "SQL", "status": "learn from scratch"},
        {"skill": "System Design", "status": "learn from scratch"},
    ],
    "skill_match_pct": 30,
}

revise_skills, missing_skills = _extract_skill_lists(sample_gap, "Backend Developer")

ok("Revise skills extracted", len(revise_skills) == 2)
ok("Revise skills status filtered", all(s["type"] == "revise" for s in revise_skills))
ok("Missing skills extracted", len(missing_skills) == 3)
ok("Missing skills sorted by weight descending", missing_skills[0]["weight"] >= missing_skills[-1]["weight"])

# Resources helper
res_python = _get_resources("Python")
ok("Canonical resource lookup works for Python", len(res_python) > 0 and "Python" in res_python[0])


# ═══════════════════════════════════════════════════════════════
# Section 2 – Output Validation & Sanitization
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 2: Roadmap Validation & Sanitization --")

# Empty dict input
v_empty = _validate_roadmap_output({})
ok("Empty input yields dict with 'weeks'", "weeks" in v_empty)
eq("Yields exactly 6 weeks", len(v_empty["weeks"]), 6)
ok("Each week has week number 1..6", [w["week"] for w in v_empty["weeks"]] == [1, 2, 3, 4, 5, 6])
ok("Each week has theme and tasks", all("theme" in w and "tasks" in w for w in v_empty["weeks"]))

# Incomplete input (3 weeks provided)
v_partial = _validate_roadmap_output({
    "weeks": [
        {"week": 1, "theme": "Foundations", "tasks": [{"task": "Task 1", "completed": False}]},
        {"week": 2, "theme": "Basics", "tasks": ["Task 2 string"]},
    ]
})
eq("Partial 2-week input padded to 6 weeks", len(v_partial["weeks"]), 6)
ok("Week 1 tasks preserved", v_partial["weeks"][0]["tasks"][0]["task"] == "Task 1")
ok("Week 2 string task coerced to dict", isinstance(v_partial["weeks"][1]["tasks"][0], dict))
eq("Coerced task completed=False", v_partial["weeks"][1]["tasks"][0]["completed"], False)


# ═══════════════════════════════════════════════════════════════
# Section 3 – Deterministic Roadmap Fallback
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 3: Deterministic Roadmap Fallback --")

fallback_rm = _deterministic_roadmap_fallback(sample_gap, "Backend Developer")

ok("Fallback produces valid dict", isinstance(fallback_rm, dict))
eq("Fallback has 6 weeks", len(fallback_rm["weeks"]), 6)

w1 = fallback_rm["weeks"][0]
w3 = fallback_rm["weeks"][2]
w6 = fallback_rm["weeks"][5]

ok("Week 1 contains [REVISE] tasks", any("[REVISE]" in t["task"] for t in w1["tasks"]))
ok("Week 3 contains [LEARN] tasks", any("[LEARN]" in t["task"] for t in w3["tasks"]))
ok("Week 6 contains [PROJECT & RESUME] tasks", any("[PROJECT" in t["task"] for t in w6["tasks"]))


# ═══════════════════════════════════════════════════════════════
# Section 4 – End-to-End Roadmap Generator
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 4: End-to-End Roadmap Generation --")

# CSE Sem 4 student targeting Full Stack Developer
cse_gap = analyze_skill_gap("CSE", 4, "Full Stack Developer", ["C++", "Algorithms"])
cse_roadmap = generate_personalized_roadmap(cse_gap, "Full Stack Developer")

ok("Roadmap generated for CSE student", isinstance(cse_roadmap, dict))
eq("Contains 6 weeks", len(cse_roadmap.get("weeks", [])), 6)

for w in cse_roadmap["weeks"]:
    ok(f"Week {w['week']} has non-empty theme", bool(w.get("theme")))
    ok(f"Week {w['week']} has tasks", len(w.get("tasks", [])) > 0)
    for t in w["tasks"]:
        ok("Task has 'task' string", isinstance(t.get("task"), str) and len(t["task"]) > 0)
        ok("Task has 'completed' boolean", isinstance(t.get("completed"), bool))

# ECE Sem 5 student targeting Embedded Systems Engineer
ece_gap = analyze_skill_gap("ECE", 5, "Embedded Systems Engineer", ["C", "Microcontrollers"])
ece_roadmap = generate_personalized_roadmap(ece_gap, "Embedded Systems Engineer")

ok("Roadmap generated for ECE student", isinstance(ece_roadmap, dict))
eq("Contains 6 weeks", len(ece_roadmap.get("weeks", [])), 6)


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
