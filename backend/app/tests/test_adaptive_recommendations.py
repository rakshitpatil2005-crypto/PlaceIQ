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
from app.models import AssessmentAttempt, GapReport, LearningCourse, Roadmap, User
from app.routers.learning_router import router as learning_router
from app.services.adaptive_recommendations import build_recommendations


@pytest.fixture
def recommendation_app() -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    with testing_session_local() as db:
        learner = User(
            name="Recommendation Learner",
            email="recommendation@example.test",
            hashed_password="hash",
            branch="CSE",
            semester=5,
            target_role="Backend Developer",
        )
        other = User(name="Other Learner", email="recommendation-other@example.test", hashed_password="hash")
        db.add_all([learner, other])
        db.commit()
        db.refresh(learner)
        db.refresh(other)
        learner_id, other_id = learner.id, other.id

        db.add(
            LearningCourse(
                user_id=learner_id,
                skill_id="SQL",
                content={
                    "lessons": [
                        {
                            "lesson_id": "lesson-1",
                            "title": "SQL joins",
                            "key_takeaways": ["Choose a join based on related rows."],
                        }
                    ]
                },
                context={"target_role": "Backend Developer"},
                completed_lessons=["lesson-1"],
            )
        )
        db.add(
            LearningCourse(
                user_id=learner_id,
                skill_id="Python",
                content={"lessons": [{"lesson_id": "lesson-1", "title": "Python basics"}]},
                context={},
                completed_lessons=[],
            )
        )
        db.add(
            Roadmap(
                user_id=learner_id,
                weeks=[
                    {
                        "week": 1,
                        "theme": "Foundations",
                        "tasks": [
                            {"task": "[LEARN] JavaScript Fundamentals", "completed": False},
                            {"task": "[LEARN] Unknown Platform Topic", "completed": False},
                            {"task": "[LEARN] Java Fundamentals", "completed": True},
                        ],
                    }
                ],
            )
        )
        db.add(
            GapReport(
                user_id=learner_id,
                target_role="Backend Developer",
                covered_by_syllabus=[],
                from_resume=[],
                missing=[
                    {"skill": "JavaScript", "status": "learn from scratch"},
                    {"skill": "Not A Canonical Skill", "status": "learn from scratch"},
                ],
                skill_match_pct=25,
            )
        )

        older = datetime(2026, 1, 1)
        for attempt_id, outcomes in ((1, [False, True, True]), (2, [False, True, True])):
            questions = [
                {
                    "question_id": f"q{index}",
                    "concept": "SQL joins" if index == 0 else f"SQL concept {index}",
                    "is_correct": correct,
                    "answer": "wrong" if not correct else "correct",
                    "correct_answer": "correct",
                    "explanation": "The explanation supports understanding of the SQL concept.",
                }
                for index, correct in enumerate(outcomes)
            ]
            db.add(
                AssessmentAttempt(
                    id=attempt_id,
                    user_id=learner_id,
                    skill_id="SQL",
                    lesson_id="lesson-1",
                    questions=[],
                    content_source="fallback",
                    submitted_answers={},
                    result={"questions": questions},
                    submitted_at=older + timedelta(days=attempt_id),
                )
            )
        db.add(
            AssessmentAttempt(
                user_id=learner_id,
                skill_id="Python",
                lesson_id="lesson-1",
                questions=[],
                content_source="fallback",
                submitted_answers={},
                result={
                    "questions": [
                        {
                            "question_id": f"p{index}",
                            "concept": "Python basics",
                            "is_correct": True,
                            "answer": "correct",
                            "correct_answer": "correct",
                            "explanation": "A short explanation supports the learner.",
                        }
                        for index in range(3)
                    ]
                },
                submitted_at=older + timedelta(days=3),
            )
        )
        db.commit()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(learning_router)
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield {
        "client": client,
        "headers": {"Authorization": f"Bearer {create_access_token({'sub': str(learner_id)})}"},
        "other_headers": {"Authorization": f"Bearer {create_access_token({'sub': str(other_id)})}"},
        "session_factory": testing_session_local,
        "user_id": learner_id,
    }
    client.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_recommendations_prioritize_repeated_weakness_without_calling_it_mastery() -> None:
    from app.models import User

    user = User(id=10, branch="CSE", semester=5, target_role="Backend Developer")
    recommendations = build_recommendations(
        user=user,
        mastery_by_skill=[
            {
                "skill_id": "SQL",
                "status": "developing",
                "score_pct": 66.7,
                "latest_assessment_score_pct": 66.7,
                "evidence_assessments": 2,
                "evidence_questions": 6,
                "assessments": [
                    {
                        "assessment_id": 1,
                        "lesson_id": "lesson-1",
                        "question_review": [{"concept": "Joins", "is_correct": False}],
                    }
                ],
                "concepts": [
                    {
                        "concept": "Joins",
                        "status": "review",
                        "correct": 0,
                        "total": 2,
                        "evidence_assessments": 2,
                    }
                ],
            }
        ],
        roadmap_candidates=[
            {"skill_id": "JavaScript", "task": "[LEARN] JavaScript Fundamentals", "week": 1, "priority": (0, 0)}
        ],
        gap_candidates=[],
        lessons_by_skill={
            "SQL": {"lesson-1": {"title": "SQL joins"}},
            "JavaScript": {},
        },
    )

    assert recommendations[0]["skill_id"] == "SQL"
    assert recommendations[0]["action"] == "revise"
    assert recommendations[0]["concept"] == "Joins"
    assert "0/2 correct" in recommendations[0]["reason"]
    assert recommendations[0]["evidence"]
    assert recommendations[0]["next_step"]
    assert recommendations[1]["skill_id"] == "JavaScript"
    assert recommendations[1]["action"] == "study"
    assert "not evidence of failure" in recommendations[1]["evidence"][1]


def test_recommendation_api_returns_evidence_context_and_skips_unmapped_tasks(recommendation_app: dict) -> None:
    response = recommendation_app["client"].get(
        "/learning/recommendations",
        headers=recommendation_app["headers"],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["profile_context"] == {
        "target_role": "Backend Developer",
        "branch": "CSE",
        "semester": 5,
    }
    recommendations = payload["recommendations"]
    assert recommendations[0]["skill_id"] == "SQL"
    assert recommendations[0]["action"] == "revise"
    assert recommendations[0]["context"]["target_role"] == "Backend Developer"
    assert recommendations[0]["context"]["branch"] == "CSE"
    assert recommendations[0]["context"]["semester"] == 5
    assert recommendations[1]["skill_id"] == "Python"
    assert recommendations[1]["action"] == "reassess"
    assert any(item["skill_id"] == "JavaScript" for item in recommendations)
    assert all(item["skill_id"] != "Unknown Platform Topic" for item in recommendations)
    assert all(item["reason"] and item["evidence"] and item["next_step"] for item in recommendations)


def test_recommendations_validate_requested_skill_and_remain_user_scoped(recommendation_app: dict) -> None:
    client = recommendation_app["client"]
    headers = recommendation_app["headers"]
    other_headers = recommendation_app["other_headers"]

    assert client.get("/learning/recommendations").status_code == 401
    assert client.get("/learning/recommendations?skill_id=UnknownSkill", headers=headers).status_code == 404

    selected = client.get("/learning/recommendations?skill_id=JavaScript", headers=headers)
    assert selected.status_code == 200
    assert all(item["skill_id"] == "JavaScript" for item in selected.json()["recommendations"])

    other = client.get("/learning/recommendations", headers=other_headers)
    assert other.status_code == 200
    assert other.json()["recommendations"] == []
    assert other.json()["profile_context"] == {}


def test_recommendations_do_not_mutate_assessment_or_roadmap_records(recommendation_app: dict) -> None:
    client = recommendation_app["client"]
    with recommendation_app["session_factory"]() as db:
        assessments_before = [
            (item.id, item.result, item.submitted_answers)
            for item in db.query(AssessmentAttempt).filter(
                AssessmentAttempt.user_id == recommendation_app["user_id"]
            ).order_by(AssessmentAttempt.id)
        ]
        roadmap_before = (
            db.query(Roadmap)
            .filter(Roadmap.user_id == recommendation_app["user_id"])
            .one()
            .weeks
        )

    client.get("/learning/recommendations", headers=recommendation_app["headers"])

    with recommendation_app["session_factory"]() as db:
        assessments_after = [
            (item.id, item.result, item.submitted_answers)
            for item in db.query(AssessmentAttempt).filter(
                AssessmentAttempt.user_id == recommendation_app["user_id"]
            ).order_by(AssessmentAttempt.id)
        ]
        roadmap_after = (
            db.query(Roadmap)
            .filter(Roadmap.user_id == recommendation_app["user_id"])
            .one()
            .weeks
        )
    assert assessments_after == assessments_before
    assert roadmap_after == roadmap_before
