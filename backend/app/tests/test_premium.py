from collections.abc import Generator
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.config import settings
from app.database import Base, get_db
from app.models import (
    AssessmentAttempt,
    GapReport,
    InterviewSession,
    PremiumAccessRequest,
    PremiumSubscription,
    ReadinessScore,
    ReadinessScoreHistory,
    Resume,
    Roadmap,
    User,
)
from app.routers.learning_router import router as learning_router
from app.routers.premium_router import router as premium_router


@pytest.fixture
def premium_app(monkeypatch) -> Generator[dict, None, None]:
    monkeypatch.setattr(settings, "PREMIUM_AMOUNT_MINOR", None)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    with session_factory() as db:
        learner = User(
            name="Premium Learner",
            email="premium-learner@example.test",
            hashed_password="hash",
            role="student",
            target_role="Backend Developer",
        )
        other = User(
            name="Other Learner",
            email="other-premium@example.test",
            hashed_password="hash",
            role="student",
            target_role="Data Analyst",
        )
        admin = User(
            name="Plan Admin",
            email="premium-admin@example.test",
            hashed_password="hash",
            role="admin",
        )
        db.add_all([learner, other, admin])
        db.commit()
        user_ids = {"learner": learner.id, "other": other.id, "admin": admin.id}

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(premium_router)
    app.include_router(learning_router)
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    headers = {
        key: {
            "Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"
        }
        for key, user_id in user_ids.items()
    }
    yield {
        "client": client,
        "headers": headers,
        "session_factory": session_factory,
        "user_ids": user_ids,
    }
    client.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_existing_users_default_to_core_and_can_still_use_core_features(
    premium_app: dict,
) -> None:
    plan = premium_app["client"].get(
        "/premium/plan",
        headers=premium_app["headers"]["learner"],
    )
    mastery = premium_app["client"].get(
        "/learning/mastery",
        headers=premium_app["headers"]["learner"],
    )

    assert plan.status_code == 200
    assert plan.json()["plan"] == "free"
    assert plan.json()["entitlement_status"] == "inactive"
    assert plan.json()["pricing"]["payment_provider_configured"] is False
    assert mastery.status_code == 200
    assert mastery.json()["skills"] == []


def test_access_request_does_not_upgrade_user_or_modify_saved_records(
    premium_app: dict,
) -> None:
    session_factory = premium_app["session_factory"]
    user_id = premium_app["user_ids"]["learner"]
    with session_factory() as db:
        db.add(
            Resume(
                user_id=user_id,
                filename="resume.pdf",
                raw_text="private resume text",
                extracted_skills=["Python"],
                projects=[{"name": "Service", "tech": ["Python"]}],
                ats_score=81,
            )
        )
        db.add(
            Roadmap(
                user_id=user_id,
                weeks=[{"week": 1, "tasks": [{"task": "Study Python", "completed": True}]}],
            )
        )
        db.commit()

    response = premium_app["client"].post(
        "/premium/access-request",
        headers=premium_app["headers"]["learner"],
    )
    repeated = premium_app["client"].post(
        "/premium/access-request",
        headers=premium_app["headers"]["learner"],
    )

    assert response.status_code == 201
    assert response.json()["status"] == "request_recorded"
    assert response.json()["plan"] == "free"
    assert "No payment was taken" in response.json()["message"]
    assert repeated.json()["access_request_pending"] is True
    with session_factory() as db:
        assert db.query(PremiumAccessRequest).filter_by(user_id=user_id).count() == 1
        assert db.query(PremiumSubscription).filter_by(user_id=user_id).count() == 0
        assert db.query(Resume).filter_by(user_id=user_id).count() == 1
        assert db.query(Roadmap).filter_by(user_id=user_id).count() == 1


def test_premium_overview_is_server_gated_and_requires_authentication(
    premium_app: dict,
) -> None:
    free_response = premium_app["client"].get(
        "/premium/overview",
        headers=premium_app["headers"]["learner"],
    )
    anonymous_response = premium_app["client"].get("/premium/overview")

    assert free_response.status_code == 403
    assert "active Premium access" in free_response.json()["detail"]
    assert anonymous_response.status_code == 401


def test_premium_overview_uses_only_authenticated_user_saved_evidence(
    premium_app: dict,
) -> None:
    session_factory = premium_app["session_factory"]
    user_id = premium_app["user_ids"]["learner"]
    other_id = premium_app["user_ids"]["other"]
    with session_factory() as db:
        db.add_all([
            PremiumSubscription(user_id=user_id, plan="premium", status="active"),
            Resume(
                user_id=user_id,
                filename="resume.pdf",
                raw_text="private resume text",
                extracted_skills=["Python", "SQL"],
                projects=[{"name": "API", "tech": ["Python"]}],
                ats_score=82.5,
            ),
            GapReport(
                user_id=user_id,
                target_role="Backend Developer",
                covered_by_syllabus=[{"skill": "SQL", "status": "covered"}],
                from_resume=["Python"],
                missing=[{"skill": "System Design"}],
                skill_match_pct=73,
            ),
            Roadmap(
                user_id=user_id,
                weeks=[{"week": 1, "tasks": [
                    {"task": "Review Python", "completed": True},
                    {"task": "Study SQL", "completed": False},
                ]}],
            ),
            InterviewSession(
                user_id=user_id,
                target_role="Backend Developer",
                questions=[{"question": "Q1"}, {"question": "Q2"}],
                answers=[],
                scores=[
                    {
                        "question_index": 0,
                        "question_type": "technical_mcq",
                        "score_out_of_10": 8,
                        "is_correct": True,
                        "selected_option": "choice-secret",
                        "correct_answer": "answer-key-secret",
                        "question": "private interview question",
                        "explanation": "The submitted choice uses the expected method.",
                    },
                    {"question_index": 1, "score_out_of_10": 7},
                ],
                overall_score=75,
                weak_skills=["System Design"],
            ),
            ReadinessScore(
                user_id=user_id,
                resume_score=82.5,
                skill_score=73,
                roadmap_score=50,
                interview_score=75,
                total=72.13,
            ),
            ReadinessScoreHistory(
                user_id=user_id,
                resume_score=80,
                skill_score=70,
                roadmap_score=50,
                interview_score=70,
                total=69,
                created_at=datetime.utcnow() - timedelta(days=1),
            ),
            AssessmentAttempt(
                user_id=user_id,
                skill_id="Python",
                lesson_id="lesson-1",
                questions=[],
                content_source="fallback",
                result={"correct": 3, "total": 4, "questions": []},
                submitted_at=datetime.utcnow(),
            ),
            Resume(
                user_id=other_id,
                filename="other.pdf",
                raw_text="must not leak",
                extracted_skills=["SecretSkill"],
                projects=[],
                ats_score=99,
            ),
        ])
        db.commit()

    response = premium_app["client"].get(
        "/premium/overview",
        headers=premium_app["headers"]["learner"],
    )
    data = response.json()

    assert response.status_code == 200
    assert data["analytics"]["readiness_current"]["total"] == 72.13
    assert data["analytics"]["readiness_history"][0]["total"] == 69
    assert data["analytics"]["roadmap_progress"] == {
        "completed_tasks": 1,
        "total_tasks": 2,
        "weeks": 1,
    }
    assert data["analytics"]["assessment_accuracy"] == {
        "assessments": 1,
        "correct": 3,
        "questions": 4,
        "accuracy_pct": 75,
    }
    assert data["placement_report"]["resume"]["skills"] == ["Python", "SQL"]
    assert data["placement_report"]["skill_gap"]["missing"] == [{"skill": "System Design"}]
    assert data["placement_report"]["latest_interview"]["weak_skills"] == ["System Design"]
    interview_feedback = data["placement_report"]["latest_interview"]["feedback"]
    assert interview_feedback[0]["explanation"] == "The submitted choice uses the expected method."
    assert interview_feedback[0]["is_correct"] is True
    assert "correct_answer" not in interview_feedback[0]
    assert "selected_option" not in interview_feedback[0]
    assert "question" not in interview_feedback[0]
    assert "answer-key-secret" not in response.text
    assert "raw_text" not in data["placement_report"]["resume"]
    assert "SecretSkill" not in response.text


def test_student_cannot_self_activate_but_admin_can_manually_provision_access(
    premium_app: dict,
) -> None:
    student_attempt = premium_app["client"].put(
        f"/premium/admin/users/{premium_app['user_ids']['learner']}/entitlement",
        json={"active": True},
        headers=premium_app["headers"]["learner"],
    )
    admin_activation = premium_app["client"].put(
        f"/premium/admin/users/{premium_app['user_ids']['learner']}/entitlement",
        json={"active": True},
        headers=premium_app["headers"]["admin"],
    )
    plan = premium_app["client"].get(
        "/premium/plan",
        headers=premium_app["headers"]["learner"],
    )

    assert student_attempt.status_code == 403
    assert admin_activation.status_code == 200
    assert "not a payment confirmation" in admin_activation.json()["notice"]
    assert plan.json()["plan"] == "premium"
    assert plan.json()["entitlement_status"] == "active"

    admin_deactivation = premium_app["client"].put(
        f"/premium/admin/users/{premium_app['user_ids']['learner']}/entitlement",
        json={"active": False},
        headers=premium_app["headers"]["admin"],
    )
    deactivated_plan = premium_app["client"].get(
        "/premium/plan",
        headers=premium_app["headers"]["learner"],
    )
    assert admin_deactivation.status_code == 200
    assert admin_deactivation.json()["entitlement_status"] == "inactive"
    assert deactivated_plan.json()["plan"] == "free"
    assert deactivated_plan.json()["entitlement_status"] == "inactive"


def test_frontend_cannot_supply_a_plan_to_upgrade(
    premium_app: dict,
) -> None:
    response = premium_app["client"].post(
        "/premium/access-request",
        json={"plan": "premium", "is_premium": True},
        headers=premium_app["headers"]["learner"],
    )

    assert response.status_code == 201
    assert response.json()["plan"] == "free"
