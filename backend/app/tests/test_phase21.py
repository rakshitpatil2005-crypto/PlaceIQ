"""
Phase 2.1 Skill Intelligence Tests
Run from: backend/
  python -m pytest app/tests/test_phase21.py -v
or:
  python -m app.tests.test_phase21
"""
import sys
import os
import io
# Force UTF-8 output so box/emoji chars don't break Windows CP1252 console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from app.services.skill_extractor import normalize_skill, normalize_skills_list
from app.services.gap_analyzer import (
    _skills_match, _skill_in_set, _normalize_skill_set,
    get_role_requirements, analyze_skill_gap
)

PASS = "\033[92m✔\033[0m"
FAIL = "\033[91m✘\033[0m"
_total = _passed = 0

def check(desc: str, got, expected):
    global _total, _passed
    _total += 1
    ok = got == expected
    if ok:
        _passed += 1
    icon = PASS if ok else FAIL
    print(f"  {icon} {desc}")
    if not ok:
        print(f"      got      : {got!r}")
        print(f"      expected : {expected!r}")

def check_true(desc: str, expr: bool):
    global _total, _passed
    _total += 1
    if expr:
        _passed += 1
    icon = PASS if expr else FAIL
    print(f"  {icon} {desc}")


# ═══════════════════════════════════════════════════════════════
# Section 1 – normalize_skill: exact alias matches
# ═══════════════════════════════════════════════════════════════
print("\n── Section 1: Exact alias normalization ──")
check("'python' → 'Python'",           normalize_skill("python"),           "Python")
check("'Python3' → 'Python'",          normalize_skill("Python3"),          "Python")
check("'reactjs' → 'React'",           normalize_skill("reactjs"),          "React")
check("'react.js' → 'React'",          normalize_skill("react.js"),         "React")
check("'React.js' → 'React'",          normalize_skill("React.js"),         "React")
check("'js' → 'JavaScript'",           normalize_skill("js"),               "JavaScript")
check("'ES6' → 'JavaScript'",          normalize_skill("ES6"),              "JavaScript")
check("'cpp' → 'C++'",                 normalize_skill("cpp"),              "C++")
check("'c plus plus' → 'C++'",         normalize_skill("c plus plus"),      "C++")
check("'c programming' → 'C'",         normalize_skill("c programming"),    "C")
check("'mysql' → 'SQL'",               normalize_skill("mysql"),            "SQL")
check("'postgresql' → 'PostgreSQL'",   normalize_skill("postgresql"),       "PostgreSQL")
check("'rdbms' → 'SQL'",               normalize_skill("rdbms"),            "SQL")
check("'dsa' → 'Data Structures'",     normalize_skill("dsa"),              "Data Structures")
check("'nodejs' → 'Node.js'",          normalize_skill("nodejs"),           "Node.js")
check("'node.js' → 'Node.js'",         normalize_skill("node.js"),          "Node.js")
check("'ml' → 'Machine Learning'",     normalize_skill("ml"),               "Machine Learning")
check("'dl' → 'Deep Learning'",        normalize_skill("dl"),               "Deep Learning")
check("'sklearn' → 'Machine Learning'",normalize_skill("sklearn"),          "Machine Learning")
check("'tensorflow' → 'Deep Learning'",normalize_skill("tensorflow"),       "Deep Learning")
check("'github' → 'Git'",              normalize_skill("github"),           "Git")
check("'iot' → 'IoT'",                 normalize_skill("iot"),              "IoT")
check("'oop' → 'Object-Oriented Programming'", normalize_skill("oop"),     "Object-Oriented Programming")
check("'oops' → 'Object-Oriented Programming'", normalize_skill("oops"),   "Object-Oriented Programming")
check("'powerbi' → 'PowerBI'",         normalize_skill("powerbi"),          "PowerBI")
check("'power bi' → 'PowerBI'",        normalize_skill("power bi"),         "PowerBI")
check("'aws' → 'AWS'",                 normalize_skill("aws"),              "AWS")
check("'verilog' → 'Verilog'",         normalize_skill("verilog"),          "Verilog")
check("'VHDL' → 'VHDL'",              normalize_skill("VHDL"),             "VHDL")
check("'restful api' → 'REST APIs'",   normalize_skill("restful api"),      "REST APIs")
check("'rest api' → 'REST APIs'",      normalize_skill("rest api"),         "REST APIs")
check("'linux' → 'Linux'",             normalize_skill("linux"),            "Linux")
check("'docker' → 'Docker'",           normalize_skill("docker"),           "Docker")
check("'kubernetes' → 'Kubernetes'",   normalize_skill("kubernetes"),       "Kubernetes")
check("'k8s' → 'Kubernetes'",          normalize_skill("k8s"),              "Kubernetes")

# ═══════════════════════════════════════════════════════════════
# Section 2 – normalize_skill: fuzzy / near-miss matches
# ═══════════════════════════════════════════════════════════════
print("\n── Section 2: Fuzzy near-miss normalization ──")
check_true("'ReactJS' fuzzy → 'React'",     normalize_skill("ReactJS") == "React")
check_true("'Node JS' fuzzy → 'Node.js'",   normalize_skill("Node JS") == "Node.js")
check_true("'Mongo DB' fuzzy → 'MongoDB'",  normalize_skill("Mongo DB") == "MongoDB")
check_true("'Scikit Learn' fuzzy → ML",     normalize_skill("Scikit Learn") == "Machine Learning")
check_true("'angular js' → 'Angular'",      normalize_skill("angular js") == "Angular")

# Unknown skill falls back gracefully
unknown = normalize_skill("QuibbleScript")
check_true("Unknown skill falls back to Title-case", unknown == "Quiblescript" or unknown[0].isupper())

# ═══════════════════════════════════════════════════════════════
# Section 3 – normalize_skills_list deduplication
# ═══════════════════════════════════════════════════════════════
print("\n── Section 3: normalize_skills_list deduplication ──")
raw = ["python", "Python3", "reactjs", "React.js", "js", "JavaScript", "mysql", "sql"]
result = normalize_skills_list(raw)
check_true("Python appears once",     result.count("Python") == 1)
check_true("React appears once",      result.count("React") == 1)
check_true("JavaScript appears once", result.count("JavaScript") == 1)
check_true("SQL appears once",        result.count("SQL") == 1)
check_true("Result has 4 items",      len(result) == 4)

# ═══════════════════════════════════════════════════════════════
# Section 4 – _skills_match
# ═══════════════════════════════════════════════════════════════
print("\n── Section 4: _skills_match ──")
check_true("React == ReactJS",        _skills_match("React", "ReactJS"))
check_true("SQL == MySQL",            _skills_match("SQL", "MySQL"))
check_true("Node.js == nodejs",       _skills_match("Node.js", "nodejs"))
check_true("ML == Machine Learning",  _skills_match("ML", "Machine Learning"))
check_true("Python != Java",         not _skills_match("Python", "Java"))
check_true("SQL != NoSQL",           not _skills_match("SQL", "NoSQL"))

# ═══════════════════════════════════════════════════════════════
# Section 5 – _skill_in_set
# ═══════════════════════════════════════════════════════════════
print("\n── Section 5: _skill_in_set ──")
skill_set = {"Python", "Machine Learning", "SQL", "React"}
check_true("'python' in set",       _skill_in_set("python", skill_set))
check_true("'ml' in set",           _skill_in_set("ml", skill_set))
check_true("'mysql' in set",        _skill_in_set("mysql", skill_set))
check_true("'reactjs' in set",      _skill_in_set("reactjs", skill_set))
check_true("'Java' NOT in set",    not _skill_in_set("Java", skill_set))

# ═══════════════════════════════════════════════════════════════
# Section 6 – get_role_requirements
# ═══════════════════════════════════════════════════════════════
print("\n── Section 6: get_role_requirements ──")
ml_role = get_role_requirements("ML Engineer")
check_true("ML Engineer has Python",          "Python" in ml_role)
check_true("ML Engineer has Machine Learning","Machine Learning" in ml_role)
check_true("ML Engineer weights are ints",    all(isinstance(v, int) for v in ml_role.values()))

# Fuzzy role match
fuzzy_role = get_role_requirements("Backend Developer")
check_true("Backend Developer fetched",       len(fuzzy_role) > 0)

be_role = get_role_requirements("backend developer")  # case insensitive
check_true("'backend developer' (lower) fetched", len(be_role) > 0)

# ═══════════════════════════════════════════════════════════════
# Section 7 – analyze_skill_gap (full pipeline)
# ═══════════════════════════════════════════════════════════════
print("\n── Section 7: analyze_skill_gap ──")

# CSE student in sem 6 with some resume skills
gap = analyze_skill_gap(
    branch="CSE",
    current_sem=6,
    target_role="Full Stack Developer",
    resume_skills=["reactjs", "nodejs", "mysql", "github", "javascript"]
)
check_true("Returns dict",               isinstance(gap, dict))
check_true("Has target_role",            "target_role" in gap)
check_true("Has skill_match_pct",        "skill_match_pct" in gap)
check_true("Match pct is int/float",     isinstance(gap["skill_match_pct"], (int, float)))
check_true("Match pct 0-100",            0 <= gap["skill_match_pct"] <= 100)
check_true("CSE sem6 Full Stack match > 60%", gap["skill_match_pct"] > 60)

# ECE student targeting Embedded Systems Engineer
gap2 = analyze_skill_gap(
    branch="ECE",
    current_sem=6,
    target_role="Embedded Systems Engineer",
    resume_skills=["C", "arduino", "esp32", "pcb"]
)
check_true("ECE Embedded match > 50%",   gap2["skill_match_pct"] > 50)

# Student with aliases that need normalization
gap3 = analyze_skill_gap(
    branch="CSE",
    current_sem=7,
    target_role="Data Analyst",
    resume_skills=["python3", "postgresql", "ms excel", "power bi", "pandas"]
)
check_true("Alias-heavy Data Analyst match > 50%", gap3["skill_match_pct"] > 50)

# ═══════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════
print(f"\n{'═'*55}")
print(f"  RESULTS: {_passed}/{_total} passed", end="")
if _passed == _total:
    print("  🎉 All tests passed!")
else:
    print(f"  ({_total - _passed} failed)")
print('═'*55)
sys.exit(0 if _passed == _total else 1)
