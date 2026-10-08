"""
Phase 3.2 Roadmap Task Tracking & SQLite Persistence Tests
Run from: backend/
  python -m app.tests.test_phase32
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
from app.models import User, Roadmap
from app.routers.roadmap_router import (
    toggle_roadmap_task,
    update_roadmap_progress,
    TaskToggleRequest,
    RoadmapUpdateRequest,
)
from app.routers.dashboard_router import get_dashboard_stats

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
# Setup In-Memory Test Database
# ═══════════════════════════════════════════════════════════════
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

db = TestingSessionLocal()

# Seed test user and roadmap
test_user = User(
    name="Roadmap Tester",
    email="tester@vtu.ac.in",
    hashed_password="hashed_pw",
    branch="CSE",
    semester=5,
    target_role="Backend Developer",
)
db.add(test_user)
db.commit()
db.refresh(test_user)

initial_weeks = [
    {
        "week": 1,
        "theme": "Week 1: Fundamentals",
        "tasks": [
            {"task": "Task 1.1", "completed": False},
            {"task": "Task 1.2", "completed": False},
        ],
    },
    {
        "week": 2,
        "theme": "Week 2: Advanced Topics",
        "tasks": [
            {"task": "Task 2.1", "completed": False},
            {"task": "Task 2.2", "completed": False},
        ],
    },
]

test_roadmap = Roadmap(user_id=test_user.id, weeks=initial_weeks)
db.add(test_roadmap)
db.commit()
db.refresh(test_roadmap)


# ═══════════════════════════════════════════════════════════════
# Section 1 – Task Toggle Endpoint (Explicit completion=True)
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 1: Task Toggle (Explicit completion=True) --")

req_explicit = TaskToggleRequest(week_index=0, task_index=0, completed=True)
res_explicit = toggle_roadmap_task(req_explicit, current_user=test_user, db=db)

ok("Toggle returns response dict", isinstance(res_explicit, dict))
ok("Response has updated roadmap", "roadmap" in res_explicit)

# Verify SQLite persistence
saved_rm = db.query(Roadmap).filter(Roadmap.user_id == test_user.id).order_by(Roadmap.id.desc()).first()
eq("Week 0 Task 0 completed=True persisted in SQLite", saved_rm.weeks[0]["tasks"][0]["completed"], True)
eq("Week 0 Task 1 remains completed=False", saved_rm.weeks[0]["tasks"][1]["completed"], False)


# ═══════════════════════════════════════════════════════════════
# Section 2 – Task Toggle Endpoint (Automatic state inversion)
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 2: Task Toggle (State inversion) --")

# Toggle back to False without providing completed param
req_invert = TaskToggleRequest(week_index=0, task_index=0)
toggle_roadmap_task(req_invert, current_user=test_user, db=db)

saved_rm2 = db.query(Roadmap).filter(Roadmap.user_id == test_user.id).order_by(Roadmap.id.desc()).first()
eq("Week 0 Task 0 toggled back to False in SQLite", saved_rm2.weeks[0]["tasks"][0]["completed"], False)


# ═══════════════════════════════════════════════════════════════
# Section 3 – Bounds Validation & Error Handling
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 3: Bounds Validation & Error Handling --")

# Invalid week index
try:
    toggle_roadmap_task(TaskToggleRequest(week_index=99, task_index=0), current_user=test_user, db=db)
    ok("Out-of-bounds week_index raises HTTPException", False)
except HTTPException as e:
    eq("Raises 400 Bad Request for invalid week_index", e.status_code, 400)

# Invalid task index
try:
    toggle_roadmap_task(TaskToggleRequest(week_index=0, task_index=99), current_user=test_user, db=db)
    ok("Out-of-bounds task_index raises HTTPException", False)
except HTTPException as e:
    eq("Raises 400 Bad Request for invalid task_index", e.status_code, 400)

# Non-existent roadmap user
dummy_user = User(id=99999, name="No Roadmap User", email="noroadmap@vtu.ac.in", hashed_password="pw")
try:
    toggle_roadmap_task(TaskToggleRequest(week_index=0, task_index=0), current_user=dummy_user, db=db)
    ok("No roadmap user raises HTTPException", False)
except HTTPException as e:
    eq("Raises 404 Not Found for user with no roadmap", e.status_code, 404)


# ═══════════════════════════════════════════════════════════════
# Section 4 – Bulk Progress Update Endpoint & Dashboard Stats
# ═══════════════════════════════════════════════════════════════
print("\n-- Section 4: Bulk Progress & Dashboard Stats --")

# Mark 2 out of 4 tasks completed (50% progress)
bulk_weeks = [
    {
        "week": 1,
        "theme": "W1",
        "tasks": [
            {"task": "T1", "completed": True},
            {"task": "T2", "completed": True},
        ],
    },
    {
        "week": 2,
        "theme": "W2",
        "tasks": [
            {"task": "T3", "completed": False},
            {"task": "T4", "completed": False},
        ],
    },
]

update_req = RoadmapUpdateRequest(weeks=bulk_weeks)
update_res = update_roadmap_progress(update_req, current_user=test_user, db=db)

ok("Bulk update returns success message", "message" in update_res)

# Check dashboard stats integration
dash_stats = get_dashboard_stats(current_user=test_user, db=db)
eq("Dashboard reflects 50% roadmap progress", dash_stats["roadmap_progress"], 50)


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
