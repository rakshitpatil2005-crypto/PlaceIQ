"""
Phase 3.3 Final Roadmap Quality & UI Verification Tests
Run from: backend/
  python -m app.tests.test_phase33
"""
import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.roadmap_generator import (
    _CANONICAL_RESOURCES,
    _get_resources,
    generate_personalized_roadmap,
    _deterministic_roadmap_fallback,
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
# Section 1 – General Resource Names Verification
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 1: General Resource Names Verification --")

ok("Resource dictionary populated", len(_CANONICAL_RESOURCES) >= 25)

# Check that resource values do not start with raw domain URLs like docs.python.org
has_raw_url_domain = False
for sk, res_list in _CANONICAL_RESOURCES.items():
    for r in res_list:
        if r.startswith("http://") or r.startswith("https://"):
            has_raw_url_domain = True
            print(f"     Raw URL domain found: {sk} -> {r}")

ok("No raw http/https URLs in resource map", not has_raw_url_domain)

res_py = _get_resources("Python")
ok("Python resource uses general name", "Official Python Documentation" in res_py or "Real Python Tutorials" in res_py)

res_react = _get_resources("React")
ok("React resource uses general name", "Official React Documentation" in res_react or "freeCodeCamp React Guides" in res_react)

res_ds = _get_resources("Data Structures")
ok("Data Structures resource uses general name", "GeeksforGeeks Data Structures" in res_ds or "LeetCode Practice" in res_ds)


# ═══════════════════════════════════════════════════════════════
# Section 2 – 6-Week Roadmap Structure & Skill Differentiation
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 2: 6-Week Roadmap Structure & Skill Differentiation --")

gap = analyze_skill_gap("CSE", 5, "Backend Developer", ["Python"])
rm = generate_personalized_roadmap(gap, "Backend Developer")

ok("Generated roadmap is a dict", isinstance(rm, dict))
ok("Has 'weeks' key", "weeks" in rm)
eq("Contains exactly 6 weeks", len(rm["weeks"]), 6)

week_numbers = [w["week"] for w in rm["weeks"]]
eq("Week numbers are 1 through 6", week_numbers, [1, 2, 3, 4, 5, 6])

all_tasks = []
for w in rm["weeks"]:
    ok(f"Week {w['week']} has non-empty theme", bool(w.get("theme")))
    ok(f"Week {w['week']} has tasks", len(w.get("tasks", [])) >= 2)
    all_tasks.extend(w["tasks"])

has_revise = any("[REVISE]" in t["task"] for t in all_tasks)
has_learn = any("[LEARN]" in t["task"] for t in all_tasks)
has_project = any("[PROJECT" in t["task"] or "project" in t["task"].lower() for t in all_tasks)

ok("Contains distinguishable [REVISE] tasks", has_revise)
ok("Contains distinguishable [LEARN] tasks", has_learn)
ok("Contains [PROJECT] capstone tasks", has_project)


# ═══════════════════════════════════════════════════════════════
# Section 3 – Deterministic Roadmap Fallback Quality
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 3: Deterministic Fallback Quality --")

fallback_rm = _deterministic_roadmap_fallback(gap, "Backend Developer")

eq("Fallback has exactly 6 weeks", len(fallback_rm["weeks"]), 6)
ok("Fallback Week 1 theme", "Foundations" in fallback_rm["weeks"][0]["theme"])
ok("Fallback Week 6 theme", "Capstone" in fallback_rm["weeks"][5]["theme"] or "Project" in fallback_rm["weeks"][5]["theme"])

f_all_tasks = [t for w in fallback_rm["weeks"] for t in w["tasks"]]

ok("Fallback has [REVISE] tasks in W1/W2", any("[REVISE]" in t["task"] for t in f_all_tasks))
ok("Fallback has [LEARN] tasks in W3/W4/W5", any("[LEARN]" in t["task"] for t in f_all_tasks))
ok("Fallback has resources in task descriptions", any("Resources:" in t["task"] for t in f_all_tasks))


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
