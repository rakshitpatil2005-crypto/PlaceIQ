"""
Phase 4.1 Core Mock Interview Engine Tests
Run from: backend/
  python -m app.tests.test_phase41
"""
import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User, Resume, GapReport, InterviewSession
from app.services.interview_generator import (
    generate_mock_interview,
    _validate_interview_output,
    _deterministic_interview_fallback,
)
from app.routers.interview_router import generate_interview_questions

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
# Section 1 – Deterministic Fallback & Question Breakdown
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 1: Fallback Generator & Question Breakdown --")

fallback_qs = _deterministic_interview_fallback(
    target_role="Embedded Systems Engineer",
    gap_skills=["IoT", "PCB Design"],
    weak_skills=["VHDL"],
    project_name="Smart Agribot",
    project_tech=["ESP32", "C++"],
)

ok("Fallback produces list", isinstance(fallback_qs, list))
eq("Produces exactly 8 questions", len(fallback_qs), 8)
ok("All items are non-empty strings", all(isinstance(q, str) and len(q) > 0 for q in fallback_qs))

# Technical questions check (first 5)
tech_qs = fallback_qs[:5]
eq("5 Technical questions generated", len(tech_qs), 5)
ok("Tech Q references weak skill 'VHDL'", any("VHDL" in q for q in tech_qs))
ok("Tech Q references project 'Smart Agribot'", any("Smart Agribot" in q for q in tech_qs))
ok("Tech Q references skill gap 'IoT'", any("IoT" in q for q in tech_qs))

# HR questions check (last 3)
hr_qs = fallback_qs[5:]
eq("3 HR questions generated", len(hr_qs), 3)
ok("HR Q covers teamwork", any("team" in q.lower() for q in hr_qs))
ok("HR Q covers adapt/pressure", any("adapt" in q.lower() or "deadline" in q.lower() for q in hr_qs))
ok("HR Q covers career goals", any("career" in q.lower() or "interested" in q.lower() for q in hr_qs))


# ═══════════════════════════════════════════════════════════════
# Section 2 – Output Validation & Sanitization
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 2: Output Validation & Sanitization --")

# Valid 8-question dict
valid_raw = {
    "target_role": "Backend Developer",
    "questions": [f"Q{i}" for i in range(1, 9)]
}
v_clean = _validate_interview_output(valid_raw, "Backend Developer")
eq("Valid 8 questions preserved", len(v_clean), 8)

# Duplicate questions & non-strings stripped
messy_raw = {
    "questions": ["Q1", "Q2", "Q1", "", None, 123, "Q3", "Q4", "Q5", "Q6", "Q7", "Q8"]
}
m_clean = _validate_interview_output(messy_raw, "Backend Developer")
ok("Duplicates, nulls, and non-strings stripped", "Q1" in m_clean and None not in m_clean)


# ═══════════════════════════════════════════════════════════════
# Section 3 – End-to-End Mock Interview Generator
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 3: End-to-End Mock Interview Generator --")

sample_projects = [
    {"name": "E-Commerce Microservice", "tech": ["Node.js", "Docker", "MongoDB"], "description": "Backend API"}
]
sample_gaps = ["Docker", "Kubernetes", "Redis"]
sample_weaks = ["System Design"]

interview = generate_mock_interview(
    target_role="Full Stack Developer",
    gap_skills=sample_gaps,
    weak_skills=sample_weaks,
    projects=sample_projects,
)

ok("Interview is dict", isinstance(interview, dict))
eq("Target role preserved", interview["target_role"], "Full Stack Developer")
ok("Contains 'questions' list", isinstance(interview.get("questions"), list))
eq("Contains exactly 8 questions", len(interview["questions"]), 8)

all_q_text = " ".join(interview["questions"])
ok("Personalized with project name or tech stack", "E-Commerce" in all_q_text or "Node.js" in all_q_text or "Full Stack" in all_q_text)


# ═══════════════════════════════════════════════════════════════
# Section 4 – Database Session Persistence
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 4: Database Session Persistence --")

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)
db = TestingSessionLocal()

test_user = User(
    name="Interview Tester",
    email="interviewer@vtu.ac.in",
    hashed_password="hashed_pw",
    branch="CSE",
    semester=6,
    target_role="Backend Developer",
)
db.add(test_user)
db.commit()

test_resume = Resume(
    user_id=test_user.id,
    filename="resume.pdf",
    extracted_skills=["Python", "SQL"],
    projects=[{"name": "Flight Booking System", "tech": ["Python", "Flask"]}],
)
db.add(test_resume)

test_gap = GapReport(
    user_id=test_user.id,
    target_role="Backend Developer",
    missing=[{"skill": "REST APIs", "status": "learn from scratch"}],
    covered_by_syllabus=[{"skill": "Operating Systems", "status": "revise and add to resume"}],
    skill_match_pct=40,
)
db.add(test_gap)
db.commit()

res_gen = generate_interview_questions(current_user=test_user, db=db)

ok("Router generate returns dict", isinstance(res_gen, dict))
eq("Target role is Backend Developer", res_gen["target_role"], "Backend Developer")
eq("Returns exactly 8 questions", len(res_gen["questions"]), 8)

# Verify SQLite persistence
saved_session = db.query(InterviewSession).filter(InterviewSession.user_id == test_user.id).order_by(InterviewSession.id.desc()).first()
ok("Session persisted in SQLite DB", saved_session is not None)
eq("Saved session target role", saved_session.target_role, "Backend Developer")
eq("Saved session has 8 questions", len(saved_session.questions), 8)


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
