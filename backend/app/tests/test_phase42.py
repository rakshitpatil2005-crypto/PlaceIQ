"""
Phase 4.2 Answer Evaluation & Feedback Persistence Tests
Run from: backend/
  python -m app.tests.test_phase42
"""
import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.database import Base
from app.models import User, InterviewSession
from app.services.interview_evaluator import (
    evaluate_candidate_answer,
    _validate_evaluation_output,
    _deterministic_evaluation_fallback,
)
from app.routers.interview_router import (
    evaluate_answer,
    get_current_interview_session,
    AnswerSubmission,
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
# Section 1 – Evaluation Validation & Sanitization
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 1: Evaluation Validation & Sanitization --")

raw_perfect = {
    "score_out_of_10": 8,
    "strengths": "Clear grasp of REST principles and HTTP methods.",
    "improvements": "Add discussion on status codes and rate limiting.",
    "feedback": "Strong response overall.",
    "ideal_answer": "REST APIs use standard HTTP verbs...",
}
v_perf = _validate_evaluation_output(raw_perfect, "What is REST?", "Backend Developer")

eq("Perfect score preserved", v_perf["score_out_of_10"], 8)
ok("Strengths preserved", bool(v_perf["strengths"]))
ok("Improvements preserved", bool(v_perf["improvements"]))
ok("Feedback preserved", bool(v_perf["feedback"]))
ok("Ideal answer preserved", bool(v_perf["ideal_answer"]))

# Messy input with string score and missing keys
raw_messy = {
    "rating": "9.4",
    "positive_points": ["Good architecture", "Clean code"],
    "areas_for_improvement": None,
}
v_messy = _validate_evaluation_output(raw_messy, "Explain Docker", "DevOps Engineer")

eq("String rating '9.4' rounded and clamped to int 9", v_messy["score_out_of_10"], 9)
ok("Positive points list converted to string strengths", "Good architecture" in v_messy["strengths"])
ok("Missing improvements filled with constructive fallback", bool(v_messy["improvements"]))
ok("Feedback fallback created", bool(v_messy["feedback"]))


# ═══════════════════════════════════════════════════════════════
# Section 2 – Deterministic Fallback Generator
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 2: Deterministic Fallback Generator --")

# Short answer
f_short = _deterministic_evaluation_fallback("What is SQL?", "SQL is a database language.", "Data Analyst")
ok("Short answer score <= 6", f_short["score_out_of_10"] <= 6)
ok("Short answer improvements highlight length", "brief" in f_short["improvements"].lower() or "too" in f_short["improvements"].lower())

# Long detailed answer
long_ans = "SQL stands for Structured Query Language. It is used to query, insert, update, and manage relational databases like PostgreSQL and MySQL using SELECT, JOIN, GROUP BY, and indexing for query optimization."
f_long = _deterministic_evaluation_fallback("What is SQL?", long_ans, "Data Analyst")
ok("Long answer score >= 7", f_long["score_out_of_10"] >= 7)
ok("Long answer strengths highlight technical depth", "depth" in f_long["strengths"].lower() or "good" in f_long["strengths"].lower() or "comprehensive" in f_long["strengths"].lower())


# ═══════════════════════════════════════════════════════════════
# Section 3 – API Evaluation & SQLite Session Persistence
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 3: API Evaluation & SQLite Persistence --")

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)
db = TestingSessionLocal()

test_user = User(
    name="Eval Tester",
    email="eval@vtu.ac.in",
    hashed_password="hashed_pw",
    branch="CSE",
    semester=6,
    target_role="Backend Developer",
)
db.add(test_user)
db.commit()

session = InterviewSession(
    user_id=test_user.id,
    target_role="Backend Developer",
    questions=[
        "Explain how database indexing works.",
        "Describe a time you resolved a team conflict.",
    ],
    answers=[],
    scores=[],
)
db.add(session)
db.commit()

# Submit answer to Q1
sub1 = AnswerSubmission(
    question="Explain how database indexing works.",
    answer="Database indexing creates a B-Tree structure to speed up data lookup from O(N) to O(log N).",
    target_role="Backend Developer",
    question_index=0,
)

eval_res = evaluate_answer(sub1, current_user=test_user, db=db)

ok("Evaluation returns dict", isinstance(eval_res, dict))
ok("Contains integer score_out_of_10 (0-10)", isinstance(eval_res.get("score_out_of_10"), int) and 0 <= eval_res["score_out_of_10"] <= 10)
ok("Contains strengths", bool(eval_res.get("strengths")))
ok("Contains improvements", bool(eval_res.get("improvements")))
ok("Contains feedback", bool(eval_res.get("feedback")))
ok("Contains ideal_answer", bool(eval_res.get("ideal_answer")))

# Verify SQLite persistence
saved_sess = db.query(InterviewSession).filter(InterviewSession.user_id == test_user.id).first()
ok("Session answers persisted in SQLite", len(saved_sess.answers) == 1)
ok("Session scores persisted in SQLite", len(saved_sess.scores) == 1)
eq("Saved score matches evaluation", saved_sess.scores[0]["score_out_of_10"], eval_res["score_out_of_10"])

# Verify GET /interview/session endpoint restoration
restored = get_current_interview_session(current_user=test_user, db=db)
ok("GET /interview/session returns session_id", "session_id" in restored)
eq("Restored answers count", len(restored["answers"]), 1)
eq("Restored scores count", len(restored["scores"]), 1)


# ═══════════════════════════════════════════════════════════════
# Section 4 – Validation Error Handling
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 4: Validation Error Handling --")

# Empty answer raises 400
try:
    evaluate_answer(AnswerSubmission(question="Q", answer="   ", target_role="Role"), current_user=test_user, db=db)
    ok("Empty answer raises HTTPException", False)
except HTTPException as e:
    eq("Empty answer raises 400 Bad Request", e.status_code, 400)

# Empty question raises 400
try:
    evaluate_answer(AnswerSubmission(question="", answer="Ans", target_role="Role"), current_user=test_user, db=db)
    ok("Empty question raises HTTPException", False)
except HTTPException as e:
    eq("Empty question raises 400 Bad Request", e.status_code, 400)


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
