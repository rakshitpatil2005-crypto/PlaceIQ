from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.database import Base, get_db
from app.models import (
    AssessmentAttempt,
    LearningCourse,
    PracticeAttempt,
    Roadmap,
    User,
)
from app.routers.learning_router import router as learning_router
from app.routers.roadmap_router import router as roadmap_router


@pytest.fixture
def feedback_loop_app() -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    lesson = {
        "lesson_id": "lesson-1",
        "title": "Python foundations",
        "introduction": "Learn essential Python foundations.",
        "explanation": "Python statements transform input data into useful output.",
        "key_takeaways": [
            "Understand Python values and expressions.",
            "Trace control flow through a Python program.",
            "Use functions to organize a Python solution.",
        ],
        "real_world_applications": ["Use a function to organize repeated steps in a small task."],
        "common_mistakes": ["Guessing without tracing the code."],
        "example_explanation": "Trace each statement to verify the program output.",
        "quick_recap": "Read the problem, apply a concept, and check the result.",
    }
    initial_weeks = [
        {
            "week": 1,
            "theme": "Foundations",
            "tasks": [
                {
                    "task_id": "python-task",
                    "task": "[LEARN] Python Fundamentals",
                    "completed": False,
                },
                {
                    "task_id": "completed-task",
                    "task": "[LEARN] Java Fundamentals",
                    "completed": True,
                    "legacy_value": "preserve",
                },
            ],
        }
    ]
    with session_factory() as db:
        learner = User(
            name="Feedback Loop Learner",
            email="feedback-loop@example.test",
            hashed_password="hash",
            branch="CSE",
            semester=5,
            target_role="Backend Developer",
        )
        other = User(name="Isolated Learner", email="isolated@example.test", hashed_password="hash")
        db.add_all([learner, other])
        db.commit()
        db.refresh(learner)
        db.refresh(other)
        user_id, other_user_id = learner.id, other.id
        db.add_all(
            [
                LearningCourse(
                    user_id=user_id,
                    skill_id="Python",
                    content={"introduction": lesson["introduction"], "lessons": [lesson]},
                    context={"target_role": "Backend Developer"},
                    completed_lessons=[],
                ),
                Roadmap(user_id=user_id, weeks=initial_weeks),
            ]
        )
        db.commit()

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(learning_router)
    app.include_router(roadmap_router)
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield {
        "client": client,
        "headers": {
            "Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"
        },
        "other_headers": {
            "Authorization": f"Bearer {create_access_token({'sub': str(other_user_id)})}"
        },
        "session_factory": session_factory,
        "user_id": user_id,
        "other_user_id": other_user_id,
        "initial_weeks": initial_weeks,
    }
    client.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _submit_assessment(client: TestClient, headers: dict) -> dict:
    started_response = client.post(
        "/learning/assessment",
        json={"skill_id": "Python", "lesson_id": "lesson-1"},
        headers=headers,
    )
    assert started_response.status_code == 200
    assessment = started_response.json()
    submitted_response = client.post(
        f"/learning/assessment/{assessment['id']}/submit",
        json={
            "answers": [
                {"question_id": question["question_id"], "answer": "b"}
                for question in assessment["questions"]
            ]
        },
        headers=headers,
    )
    assert submitted_response.status_code == 200
    return submitted_response.json()


def test_assessment_practice_recommendation_mastery_and_roadmap_feedback_loop(
    feedback_loop_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import assessment_engine, practice_engine

    monkeypatch.setattr(
        assessment_engine,
        "ask_llm_json",
        lambda prompt, retries=2: {"error": "unavailable"},
    )
    monkeypatch.setattr(
        practice_engine,
        "ask_llm_json",
        lambda prompt, retries=2: {"error": "unavailable"},
    )
    client = feedback_loop_app["client"]
    headers = feedback_loop_app["headers"]

    practice_session = client.post(
        "/learning/practice",
        json={"skill_id": "Python", "lesson_id": "lesson-1"},
        headers=headers,
    ).json()
    practice_attempt = client.post(
        f"/learning/practice/{practice_session['id']}/answers",
        json={"question_id": "q1", "answer": "b"},
        headers=headers,
    )
    assert practice_attempt.status_code == 200
    assert client.get("/learning/mastery", headers=headers).json()["skills"] == []

    first_result = _submit_assessment(client, headers)
    assert first_result["submitted"] is True
    mastery_after_first = client.get("/learning/mastery", headers=headers).json()["skills"]
    assert mastery_after_first[0]["evidence_assessments"] == 1
    assert mastery_after_first[0]["evidence_questions"] == 3
    assert mastery_after_first[0]["status"] == "insufficient_evidence"

    first_recommendations = client.get("/learning/recommendations", headers=headers).json()
    first_skill_recommendation = next(
        item
        for item in first_recommendations["recommendations"]
        if item["skill_id"] == "Python"
    )
    assert first_skill_recommendation["evidence_category"] == "insufficient_evidence"
    assert "not evidence of failure" in first_skill_recommendation["reason"]

    first_adaptation = client.post("/roadmap/adapt", headers=headers).json()
    first_task = first_adaptation["roadmap"]["weeks"][0]["tasks"][0]
    assert first_task["adaptive"]["evidence_category"] == "insufficient_evidence"
    assert first_task["task_id"] == "python-task"
    assert first_adaptation["roadmap"]["weeks"][0]["tasks"][1] == {
        "task_id": "completed-task",
        "task": "[LEARN] Java Fundamentals",
        "completed": True,
        "legacy_value": "preserve",
    }

    second_result = _submit_assessment(client, headers)
    mastery_after_second = client.get("/learning/mastery", headers=headers).json()["skills"]
    assert len(mastery_after_second) == 1
    assert mastery_after_second[0]["evidence_assessments"] == 2
    assert mastery_after_second[0]["evidence_questions"] == 6
    assert mastery_after_second[0]["status"] == "developing"
    assert any(item["status"] == "review" for item in mastery_after_second[0]["concepts"])

    refreshed_recommendations = client.get("/learning/recommendations", headers=headers).json()
    weakness_recommendation = next(
        item
        for item in refreshed_recommendations["recommendations"]
        if item["skill_id"] == "Python"
    )
    assert weakness_recommendation["evidence_category"] == "demonstrated_weakness"
    assert weakness_recommendation["href"] == "/learn?skill=Python&lesson=lesson-1"

    second_adaptation = client.post("/roadmap/adapt", headers=headers).json()
    adapted_task = second_adaptation["roadmap"]["weeks"][0]["tasks"][0]
    assert adapted_task["adaptive"]["evidence_category"] == "demonstrated_weakness"
    assert adapted_task["task_id"] == "python-task"
    repeated_adaptation = client.post("/roadmap/adapt", headers=headers).json()
    assert repeated_adaptation["roadmap"]["weeks"] == second_adaptation["roadmap"]["weeks"]
    assert repeated_adaptation["adapted_tasks"] == second_adaptation["adapted_tasks"]

    with feedback_loop_app["session_factory"]() as db:
        assert (
            db.query(AssessmentAttempt)
            .filter(AssessmentAttempt.user_id == feedback_loop_app["user_id"])
            .count()
            == 2
        )
        assert (
            db.query(PracticeAttempt)
            .filter(PracticeAttempt.user_id == feedback_loop_app["user_id"])
            .count()
            == 1
        )
        saved_roadmap = (
            db.query(Roadmap)
            .filter(Roadmap.user_id == feedback_loop_app["user_id"])
            .one()
        )
        assert [task["task_id"] for task in saved_roadmap.weeks[0]["tasks"]] == [
            "python-task",
            "completed-task",
        ]
        assert saved_roadmap.weeks[0]["tasks"][1]["completed"] is True
        saved_assessments = (
            db.query(AssessmentAttempt)
            .filter(AssessmentAttempt.user_id == feedback_loop_app["user_id"])
            .all()
        )
        assert all(attempt.result is not None for attempt in saved_assessments)


def test_feedback_loop_authentication_and_student_isolation(
    feedback_loop_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import assessment_engine

    monkeypatch.setattr(
        assessment_engine,
        "ask_llm_json",
        lambda prompt, retries=2: {"error": "unavailable"},
    )
    client = feedback_loop_app["client"]
    learner_headers = feedback_loop_app["headers"]
    other_headers = feedback_loop_app["other_headers"]
    _submit_assessment(client, learner_headers)

    assert client.get("/learning/mastery").status_code == 401
    assert client.get("/learning/recommendations").status_code == 401
    assert client.post("/roadmap/adapt").status_code == 401
    assert client.get("/learning/mastery", headers=other_headers).json()["skills"] == []
    assert client.get("/learning/recommendations", headers=other_headers).json()["recommendations"] == []
    assert client.post("/roadmap/adapt", headers=other_headers).status_code == 404

    with feedback_loop_app["session_factory"]() as db:
        user_roadmap = (
            db.query(Roadmap)
            .filter(Roadmap.user_id == feedback_loop_app["user_id"])
            .one()
        )
        assert user_roadmap.weeks[0]["tasks"][0].get("adaptive") is None
