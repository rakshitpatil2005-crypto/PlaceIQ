from collections.abc import Generator
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.database import Base, get_db
from app.models import AssessmentAttempt, GapReport, Roadmap, User
from app.routers.roadmap_router import router as roadmap_router


@pytest.fixture
def adaptive_roadmap_app() -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    with session_factory() as db:
        learner = User(
            name="Roadmap Learner",
            email="adaptive-roadmap@example.test",
            hashed_password="hash",
            branch="CSE",
            semester=5,
            target_role="Backend Developer",
        )
        other = User(
            name="Other Learner",
            email="adaptive-roadmap-other@example.test",
            hashed_password="hash",
            branch="ISE",
            semester=6,
            target_role="Frontend Developer",
        )
        db.add_all([learner, other])
        db.commit()
        db.refresh(learner)
        db.refresh(other)
        learner_id, other_id = learner.id, other.id

        learner_weeks = [
            {
                "week": 1,
                "theme": "Current roadmap",
                "tasks": [
                    {
                        "task_id": "python-task",
                        "task": "[LEARN] Python Fundamentals",
                        "completed": False,
                    },
                    {
                        "task_id": "sql-task",
                        "task": "[REVISE] SQL Fundamentals",
                        "completed": False,
                    },
                    {
                        "task_id": "javascript-task",
                        "task": "[LEARN] JavaScript Fundamentals",
                        "completed": False,
                    },
                    {
                        "task_id": "completed-task",
                        "task": "[LEARN] Java Fundamentals",
                        "completed": True,
                        "existing_note": "Keep this completed task unchanged.",
                    },
                    {
                        "task_id": "unmapped-task",
                        "task": "[PROJECT] Unknown Platform Topic",
                        "completed": False,
                    },
                ],
            }
        ]
        db.add_all(
            [
                Roadmap(user_id=learner_id, weeks=learner_weeks),
                Roadmap(
                    user_id=other_id,
                    weeks=[
                        {
                            "week": 1,
                            "theme": "Other roadmap",
                            "tasks": [
                                {
                                    "task_id": "other-js",
                                    "task": "[LEARN] JavaScript Fundamentals",
                                    "completed": False,
                                }
                            ],
                        }
                    ],
                ),
                GapReport(
                    user_id=learner_id,
                    target_role="Backend Developer",
                    covered_by_syllabus=[],
                    from_resume=[],
                    missing=[{"skill": "Python", "status": "learn from scratch"}],
                    skill_match_pct=0,
                ),
            ]
        )

        submitted = datetime(2026, 1, 1)
        for attempt_number in range(2):
            db.add(
                AssessmentAttempt(
                    user_id=learner_id,
                    skill_id="SQL",
                    lesson_id="sql-lesson",
                    questions=[],
                    content_source="fallback",
                    submitted_answers={},
                    result={
                        "questions": [
                            {
                                "question_id": f"sql-{attempt_number}-{question_number}",
                                "concept": "SQL joins",
                                "is_correct": correct,
                                "answer": "incorrect" if not correct else "correct",
                                "correct_answer": "correct",
                                "explanation": "Review join matching semantics.",
                            }
                            for question_number, correct in enumerate((False, False, True))
                        ]
                    },
                    submitted_at=submitted + timedelta(days=attempt_number),
                )
            )
        db.add(
            AssessmentAttempt(
                user_id=learner_id,
                skill_id="Python",
                lesson_id="python-lesson",
                questions=[],
                content_source="fallback",
                submitted_answers={},
                result={
                    "questions": [
                        {
                            "question_id": f"python-{index}",
                            "concept": "Python basics",
                            "is_correct": True,
                            "answer": "correct",
                            "correct_answer": "correct",
                            "explanation": "Correct response.",
                        }
                        for index in range(3)
                    ]
                },
                submitted_at=submitted + timedelta(days=3),
            )
        )
        db.commit()

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(roadmap_router)
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield {
        "client": client,
        "headers": {
            "Authorization": f"Bearer {create_access_token({'sub': str(learner_id)})}"
        },
        "other_headers": {
            "Authorization": f"Bearer {create_access_token({'sub': str(other_id)})}"
        },
        "session_factory": session_factory,
        "user_id": learner_id,
        "other_user_id": other_id,
    }
    client.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_adaptation_prioritizes_assessment_weakness_and_insufficient_evidence(
    adaptive_roadmap_app: dict,
) -> None:
    response = adaptive_roadmap_app["client"].post(
        "/roadmap/adapt",
        headers=adaptive_roadmap_app["headers"],
    )

    assert response.status_code == 200
    payload = response.json()
    tasks = payload["roadmap"]["weeks"][0]["tasks"]
    assert [task["task_id"] for task in tasks] == [
        "python-task",
        "sql-task",
        "javascript-task",
        "completed-task",
        "unmapped-task",
    ]
    assert tasks[1]["adaptive"]["priority"] == 1
    assert tasks[1]["adaptive"]["action"] == "revise"
    assert tasks[1]["adaptive"]["evidence_category"] == "demonstrated_weakness"
    assert "SQL joins" in tasks[1]["adaptive"]["reason"]
    assert tasks[0]["adaptive"]["priority"] == 2
    assert tasks[0]["adaptive"]["action"] == "reassess"
    assert tasks[0]["adaptive"]["evidence_category"] == "insufficient_evidence"
    assert "not yet enough submitted assessment evidence" in tasks[0]["adaptive"]["reason"]
    assert "not evidence of failure" in tasks[0]["adaptive"]["reason"]
    assert tasks[2]["adaptive"]["evidence_category"] == "upcoming_learning"
    assert "no demonstrated weakness" in tasks[2]["adaptive"]["reason"]
    assert "No submitted assessment evidence is available" in tasks[2]["adaptive"]["evidence"][1]
    assert tasks[3] == {
        "task_id": "completed-task",
        "task": "[LEARN] Java Fundamentals",
        "completed": True,
        "existing_note": "Keep this completed task unchanged.",
    }
    assert tasks[4] == {
        "task_id": "unmapped-task",
        "task": "[PROJECT] Unknown Platform Topic",
        "completed": False,
    }


def test_repeated_adaptation_is_idempotent_and_does_not_create_roadmaps(
    adaptive_roadmap_app: dict,
) -> None:
    client = adaptive_roadmap_app["client"]
    headers = adaptive_roadmap_app["headers"]
    first = client.post("/roadmap/adapt", headers=headers).json()
    second = client.post("/roadmap/adapt", headers=headers).json()

    assert second["roadmap"]["weeks"] == first["roadmap"]["weeks"]
    assert second["adapted_tasks"] == first["adapted_tasks"]
    with adaptive_roadmap_app["session_factory"]() as db:
        assert (
            db.query(Roadmap)
            .filter(Roadmap.user_id == adaptive_roadmap_app["user_id"])
            .count()
            == 1
        )
        assert (
            db.query(AssessmentAttempt)
            .filter(AssessmentAttempt.user_id == adaptive_roadmap_app["user_id"])
            .count()
            == 3
        )


def test_adaptation_requires_auth_and_only_changes_the_authenticated_users_roadmap(
    adaptive_roadmap_app: dict,
) -> None:
    client = adaptive_roadmap_app["client"]
    assert client.post("/roadmap/adapt").status_code == 401

    other_response = client.post(
        "/roadmap/adapt",
        headers=adaptive_roadmap_app["other_headers"],
    )
    assert other_response.status_code == 200
    other_task = other_response.json()["roadmap"]["weeks"][0]["tasks"][0]
    assert other_task["task_id"] == "other-js"
    assert other_task["adaptive"]["action"] == "study"
    assert any(
        "not evidence of failure" in evidence
        for evidence in other_task["adaptive"]["evidence"]
    )

    with adaptive_roadmap_app["session_factory"]() as db:
        learner_roadmap = (
            db.query(Roadmap)
            .filter(Roadmap.user_id == adaptive_roadmap_app["user_id"])
            .one()
        )
        assert learner_roadmap.weeks[0]["tasks"][0].get("adaptive") is None
