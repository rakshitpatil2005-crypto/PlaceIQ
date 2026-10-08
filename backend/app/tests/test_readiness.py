import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User, Resume, GapReport, Roadmap, InterviewSession, ReadinessScore, ReadinessScoreHistory
from app.services.readiness_service import compute_readiness_metrics, persist_readiness_score

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

db = TestingSessionLocal()
user = User(name="Readiness Tester", email="readiness@vtu.ac.in", hashed_password="pw", branch="CSE", semester=6, target_role="Backend Developer")
db.add(user)
db.commit()

resume = Resume(user_id=user.id, filename="resume.pdf", extracted_skills=["Python", "SQL", "Java"], projects=[{"name": "API Service", "tech": ["Python", "FastAPI"]}], ats_score=85.0)
db.add(resume)
db.commit()

gap = GapReport(user_id=user.id, target_role="Backend Developer", covered_by_syllabus=[{"skill": "SQL", "status": "covered"}], from_resume=["Python"], missing=[{"skill": "System Design", "status": "learn from scratch"}], skill_match_pct=72.0)
db.add(gap)
db.commit()

roadmap = Roadmap(user_id=user.id, weeks=[{"week": 1, "tasks": [{"task": "Task 1", "completed": True}, {"task": "Task 2", "completed": False}]}, {"week": 2, "tasks": [{"task": "Task 3", "completed": True}, {"task": "Task 4", "completed": True}]}])
db.add(roadmap)
db.commit()

session = InterviewSession(user_id=user.id, target_role="Backend Developer", questions=["Q1"], answers=[], scores=[{"question_index": 0, "question": "Q1", "score_out_of_10": 8}], overall_score=80.0, weak_skills=[])
db.add(session)
db.commit()

metrics = compute_readiness_metrics(db, user)
assert metrics["resume_score"] == 85.0
assert metrics["skill_score"] == 72.0
assert abs(metrics["roadmap_score"] - 75.0) < 1e-9
assert metrics["interview_score"] == 80.0
assert abs(metrics["total"] - 78.1) < 1e-9

snapshot = persist_readiness_score(db, user)
assert snapshot["history_written"] is True
assert abs(snapshot["total"] - 78.1) < 1e-9

current = db.query(ReadinessScore).filter(ReadinessScore.user_id == user.id).order_by(ReadinessScore.id.desc()).first()
assert current is not None
assert abs(current.total - 78.1) < 1e-9

history = db.query(ReadinessScoreHistory).filter(ReadinessScoreHistory.user_id == user.id).all()
assert len(history) == 1
assert abs(history[0].total - 78.1) < 1e-9

second_snapshot = persist_readiness_score(db, user)
assert second_snapshot["history_written"] is False
assert len(db.query(ReadinessScoreHistory).filter(ReadinessScoreHistory.user_id == user.id).all()) == 1

print("All readiness score tests passed.")
