"""
Phase 2.3 VTU 2025 Scheme & Curriculum Mapping Tests
Run from: backend/
  python -m app.tests.test_phase23
"""
import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.gap_analyzer import analyze_skill_gap, syllabus_db
from app.services.skill_extractor import normalize_skill, skills_master

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
# Section 1 – VTU 2025 Scheme Structure Verification
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 1: VTU 2025 Scheme Structure --")

ok("Syllabus DB loaded", bool(syllabus_db))
ok("CSE branch present", "CSE" in syllabus_db)
ok("ISE branch present", "ISE" in syllabus_db)
ok("ECE branch present", "ECE" in syllabus_db)

expected_sems = [str(s) for s in range(3, 9)]

for branch in ["CSE", "ISE", "ECE"]:
    bdata = syllabus_db.get(branch, {})
    present_sems = list(bdata.keys())
    ok(f"{branch} has semesters 3-8", all(s in bdata for s in expected_sems), f"got {present_sems}")


# ═══════════════════════════════════════════════════════════════
# Section 2 – Subject & Canonical Skill Mapping Integrity
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 2: Subject & Canonical Skill Integrity --")

total_subjects = 0
unmapped_skills = []

for branch, sem_map in syllabus_db.items():
    for sem, subjects in sem_map.items():
        for sub in subjects:
            total_subjects += 1
            s_name = sub.get("subject", "")
            skills = sub.get("skills", [])
            ok(f"{branch} Sem {sem}: '{s_name}' has skills", len(skills) > 0, f"subject={s_name}")
            for skill in skills:
                norm = normalize_skill(skill)
                # Verify skill maps to valid canonical or valid title-case fallback
                if not norm:
                    unmapped_skills.append(f"{branch} Sem {sem} {s_name}: {skill}")

ok(f"Total subjects verified: {total_subjects}", total_subjects >= 18)
ok("All syllabus skills map cleanly", len(unmapped_skills) == 0, f"unmapped={unmapped_skills}")


# ═══════════════════════════════════════════════════════════════
# Section 3 – Semester Progression & Skill Accumulation
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 3: Cumulative Semester Progression --")

def get_cumulative_skills(branch: str, current_sem: int) -> set[str]:
    vtu_skills = set()
    branch_data = syllabus_db.get(branch, {})
    for sem, subjects in branch_data.items():
        if int(sem) <= current_sem:
            for sub in subjects:
                for skill in sub.get("skills", []):
                    vtu_skills.add(normalize_skill(skill))
    return vtu_skills

cse_sem3 = get_cumulative_skills("CSE", 3)
cse_sem5 = get_cumulative_skills("CSE", 5)
cse_sem8 = get_cumulative_skills("CSE", 8)

ok("CSE Sem 3 has foundational skills", "Data Structures" in cse_sem3 and "C" in cse_sem3)
ok("CSE Sem 5 includes Sem 3 skills", cse_sem3.issubset(cse_sem5))
ok("CSE Sem 5 adds DBMS & Networks", "SQL" in cse_sem5 and "Computer Networks" in cse_sem5)
ok("CSE Sem 8 includes Sem 5 skills", cse_sem5.issubset(cse_sem8))
ok("CSE Sem 8 includes Cloud & ML & Cyber", "AWS" in cse_sem8 and "Machine Learning" in cse_sem8 and "Cybersecurity" in cse_sem8)

ise_sem4 = get_cumulative_skills("ISE", 4)
ise_sem7 = get_cumulative_skills("ISE", 7)
ok("ISE Sem 7 includes Sem 4 skills", ise_sem4.issubset(ise_sem7))
ok("ISE Sem 7 includes Big Data & Cloud", "Cloud" in ise_sem7 and "Machine Learning" in ise_sem7)


# ═══════════════════════════════════════════════════════════════
# Section 4 – Gap Analysis with VTU 2025 Scheme
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 4: Gap Analysis with VTU 2025 Scheme --")

# CSE Sem 3 vs Sem 8 for Full Stack Developer
gap_cse3 = analyze_skill_gap("CSE", 3, "Full Stack Developer", ["HTML", "CSS"])
gap_cse8 = analyze_skill_gap("CSE", 8, "Full Stack Developer", ["HTML", "CSS"])

ok("CSE Sem 8 match % >= CSE Sem 3 match %", gap_cse8["skill_match_pct"] >= gap_cse3["skill_match_pct"],
   f"sem3={gap_cse3['skill_match_pct']} sem8={gap_cse8['skill_match_pct']}")

# ISE Sem 6 targeting Data Analyst with Python resume skill
gap_ise6 = analyze_skill_gap("ISE", 6, "Data Analyst", ["Python", "Pandas", "PowerBI"])
ok("ISE Sem 6 Data Analyst gap computed", isinstance(gap_ise6, dict))
ok("Target role preserved", gap_ise6["target_role"] == "Data Analyst")
ok("Syllabus covered skills present", len(gap_ise6["covered_by_syllabus"]) > 0)
ok("From resume skills present", len(gap_ise6["from_resume"]) > 0)

# ECE Sem 6 targeting VLSI Engineer
gap_ece6 = analyze_skill_gap("ECE", 6, "VLSI Engineer", ["Verilog", "VHDL"])
ok("ECE Sem 6 VLSI Engineer match > 50%", gap_ece6["skill_match_pct"] > 50, f"got {gap_ece6['skill_match_pct']}")


# ═══════════════════════════════════════════════════════════════
# Section 5 – README Verification
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 5: README VTU 2025 Verification --")

# backend/app/tests/test_phase23.py -> root is 3 levels up from backend
tests_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.dirname(tests_dir)
backend_dir = os.path.dirname(app_dir)
root_dir = os.path.dirname(backend_dir)

readme_path = os.path.join(root_dir, "README.md")
readme_exists = os.path.exists(readme_path)
ok("Root README.md exists", readme_exists, f"path={readme_path}")

if readme_exists:
    with open(readme_path, "r", encoding="utf-8") as f:
        readme_content = f.read()
    ok("README mentions VTU 2025 scheme", "VTU 2025 scheme" in readme_content or "VTU 2025 Scheme" in readme_content)
    ok("README does NOT mention 2022 scheme", "2022" not in readme_content)


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
