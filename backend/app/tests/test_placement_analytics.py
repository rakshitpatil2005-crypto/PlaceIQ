from collections.abc import Generator
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import PLACEMENT_STAFF_ROLE, create_access_token
from app.database import Base, get_db
from app.models import (
    GapReport,
    InterviewSession,
    ReadinessScore,
    ReadinessScoreHistory,
    Resume,
    Roadmap,
    User,
)
from app.routers.placement_router import router as placement_router


@pytest.fixture
def placement_app() -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    with factory() as db:
        students = [
            User(
                name="Ava CSE",
                email="ava-placement@example.test",
                hashed_password="hash",
                role="student",
                branch="CSE",
                semester=5,
                target_role="Backend Developer",
            ),
            User(
                name="Ben CSE",
                email="ben-placement@example.test",
                hashed_password="hash",
                role="student",
                branch="CSE",
                semester=5,
                target_role="Backend Developer",
            ),
            User(
                name="Cam ECE",
                email="cam-placement@example.test",
                hashed_password="hash",
                role="student",
                branch="ECE",
                semester=6,
                target_role="Data Analyst",
            ),
            User(
                name="Staff",
                email="placement-staff@example.test",
                hashed_password="hash",
                role=PLACEMENT_STAFF_ROLE,
            ),
            User(
                name="Admin",
                email="placement-admin@example.test",
                hashed_password="hash",
                role="admin",
            ),
        ]
        db.add_all(students)
        db.commit()
        ids = {user.name: user.id for user in students}

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(placement_router)
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    headers = {
        name: {
            "Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"
        }
        for name, user_id in ids.items()
    }
    yield {"client": client, "factory": factory, "ids": ids, "headers": headers}
    client.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _seed_analytics_data(placement_app: dict) -> None:
    ids = placement_app["ids"]
    with placement_app["factory"]() as db:
        ava_id = ids["Ava CSE"]
        db.add_all(
            [
                Resume(
                    user_id=ava_id,
                    filename="old.pdf",
                    ats_score=100,
                    raw_text="must not be returned",
                ),
                Resume(
                    user_id=ava_id,
                    filename="latest.pdf",
                    ats_score=0,
                    raw_text="private resume text",
                ),
                GapReport(
                    user_id=ava_id,
                    target_role="Backend Developer",
                    missing=[{"skill": "Old Skill"}],
                    skill_match_pct=10,
                ),
                GapReport(
                    user_id=ava_id,
                    target_role="Backend Developer",
                    missing=[
                        {"skill": "Python"},
                        {"skill": " python "},
                        "SQL",
                        {"other": "ignored"},
                        None,
                    ],
                    skill_match_pct=50,
                ),
                Roadmap(
                    user_id=ava_id,
                    weeks=[
                        {"tasks": [{"completed": True}, {"completed": False}]},
                        "legacy malformed week",
                        {"tasks": "malformed"},
                        {"tasks": [None, {"completed": "true"}]},
                    ],
                ),
                InterviewSession(
                    user_id=ava_id,
                    target_role="Backend Developer",
                    questions=["Q1", "Q2"],
                    answers=[{"answer": "private interview answer"}],
                    scores=[
                        {"question_index": 0, "score_out_of_10": 8},
                        {"question_index": 1, "score_out_of_10": 8},
                    ],
                    overall_score=80,
                    weak_skills=["System Design", "system design"],
                ),
                InterviewSession(
                    user_id=ava_id,
                    target_role="Backend Developer",
                    questions=["Q1", "Q2"],
                    answers=[{"answer": "private in-progress answer"}],
                    scores=[{"question_index": 0, "score_out_of_10": 3}],
                    overall_score=0,
                    weak_skills=["Should not replace completed interview"],
                ),
                GapReport(
                    user_id=ids["Ben CSE"],
                    target_role="Backend Developer",
                    missing=["Python", {"skill": "Data Structures"}],
                    skill_match_pct=0,
                ),
                ReadinessScore(user_id=ava_id, total=45),
                ReadinessScoreHistory(
                    user_id=ava_id,
                    total=20,
                    created_at=datetime(2026, 1, 5),
                ),
                ReadinessScoreHistory(
                    user_id=ava_id,
                    total=70,
                    created_at=datetime(2026, 1, 20),
                ),
                ReadinessScoreHistory(
                    user_id=ava_id,
                    total=80,
                    created_at=datetime(2026, 2, 1),
                ),
            ]
        )
        db.commit()


def test_all_placement_endpoints_require_staff_or_admin(placement_app: dict) -> None:
    client = placement_app["client"]
    paths = [
        "/placement/dashboard",
        "/placement/students",
        f"/placement/students/{placement_app['ids']['Ava CSE']}",
    ]
    for path in paths:
        assert client.get(path).status_code == 401
        assert (
            client.get(path, headers=placement_app["headers"]["Ava CSE"]).status_code
            == 403
        )
        assert client.get(path, headers=placement_app["headers"]["Staff"]).status_code == 200
        assert client.get(path, headers=placement_app["headers"]["Admin"]).status_code == 200


def test_summary_uses_latest_records_denominators_and_deduplicates_students(
    placement_app: dict,
) -> None:
    _seed_analytics_data(placement_app)
    response = placement_app["client"].get(
        "/placement/dashboard?branch=cse&semester=5&target_role=backend%20developer",
        headers=placement_app["headers"]["Staff"],
    )
    assert response.status_code == 200
    result = response.json()

    assert result["cohort"] == {"student_count": 2, "status": "available"}
    assert result["readiness"]["average"] == 22.0
    assert result["readiness"]["student_count"] == 2
    assert result["readiness"]["eligible_students"] == 2
    assert result["components"]["resume"] == {
        "average": 0.0,
        "student_count": 1,
        "eligible_students": 2,
    }
    assert result["components"]["skill_gap"]["average"] == 25.0
    assert result["roadmap"]["average_progress_pct"] == 33.33
    assert result["roadmap"]["completed_tasks"] == 1
    assert result["roadmap"]["total_tasks"] == 3
    assert result["interviews"]["average_score"] == 80.0
    assert result["interviews"]["student_count"] == 1
    skills = {item["skill"]: item["student_count"] for item in result["common_missing_skills"]["skills"]}
    assert skills == {"Python": 2, "SQL": 1, "Data Structures": 1}
    assert result["readiness_trend"]["status"] == "available"
    assert result["readiness_trend"]["points"] == [
        {"month": "2026-01", "average_readiness": 70.0, "student_count": 1},
        {"month": "2026-02", "average_readiness": 80.0, "student_count": 1},
    ]


def test_student_list_filters_paginates_sorts_and_minimizes_fields(
    placement_app: dict,
) -> None:
    _seed_analytics_data(placement_app)
    client = placement_app["client"]
    headers = placement_app["headers"]["Admin"]
    first = client.get(
        "/placement/students?branch=CSE&semester=5&target_role=Backend%20Developer"
        "&page=1&page_size=1&sort_by=name&sort_order=asc",
        headers=headers,
    )
    second = client.get(
        "/placement/students?branch=CSE&semester=5&target_role=Backend%20Developer"
        "&page=2&page_size=1&sort_by=name&sort_order=asc",
        headers=headers,
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["total_students"] == 2
    assert first.json()["students"][0]["name"] == "Ava CSE"
    assert second.json()["students"][0]["name"] == "Ben CSE"
    assert "email" not in first.json()["students"][0]
    assert "password" not in str(first.json())
    assert "resume" not in str(first.json()).lower()
    assert first.json()["students"][1:] == []
    assert first.json()["students"][0]["evidence_coverage"] == {
        "available_components": 4,
        "total_components": 4,
    }


def test_student_detail_is_minimized_and_returns_only_requested_student(
    placement_app: dict,
) -> None:
    _seed_analytics_data(placement_app)
    response = placement_app["client"].get(
        f"/placement/students/{placement_app['ids']['Ava CSE']}",
        headers=placement_app["headers"]["Staff"],
    )
    assert response.status_code == 200
    result = response.json()
    assert result["student"]["name"] == "Ava CSE"
    assert result["student"]["user_id"] == placement_app["ids"]["Ava CSE"]
    assert result["readiness"]["score"] == 44.0
    assert result["skill_gap"]["missing_skills"] == ["Python", "SQL"]
    assert result["roadmap"]["progress_pct"] == 33.33
    assert result["interview"]["score"] == 80.0
    assert result["interview"]["weak_skills"] == ["System Design"]
    serialized = str(result).lower()
    assert "private resume text" not in serialized
    assert "private interview answer" not in serialized
    assert "hashed_password" not in serialized

    other = placement_app["client"].get(
        f"/placement/students/{placement_app['ids']['Cam ECE']}",
        headers=placement_app["headers"]["Staff"],
    )
    assert other.status_code == 200
    assert other.json()["student"]["user_id"] == placement_app["ids"]["Cam ECE"]
    assert other.json()["readiness"]["score"] is None
    assert "Ava CSE" not in str(other.json())


def test_empty_cohort_and_sparse_or_missing_evidence_are_explicit(
    placement_app: dict,
) -> None:
    client = placement_app["client"]
    headers = placement_app["headers"]["Staff"]
    empty = client.get(
        "/placement/dashboard?branch=ZZZ",
        headers=headers,
    ).json()
    assert empty["cohort"] == {"student_count": 0, "status": "empty"}
    assert empty["readiness"]["average"] is None
    assert empty["readiness_trend"]["status"] == "unavailable"

    summary = client.get("/placement/dashboard", headers=headers).json()
    assert summary["cohort"]["student_count"] == 3
    assert summary["readiness"]["average"] is None
    assert summary["readiness"]["student_count"] == 0
    assert summary["components"]["resume"]["average"] is None
    assert summary["components"]["resume"]["student_count"] == 0
    assert summary["readiness_trend"]["status"] == "unavailable"


def test_analytics_reads_do_not_write_readiness_or_history(placement_app: dict) -> None:
    _seed_analytics_data(placement_app)

    def snapshot() -> tuple:
        with placement_app["factory"]() as db:
            models = (
                Resume,
                GapReport,
                Roadmap,
                InterviewSession,
                ReadinessScore,
                ReadinessScoreHistory,
            )
            counts = tuple(db.query(model).count() for model in models)
            history = [
                (row.id, row.total)
                for row in db.query(ReadinessScoreHistory).order_by(
                    ReadinessScoreHistory.id
                )
            ]
            current = [
                (row.id, row.total)
                for row in db.query(ReadinessScore).order_by(ReadinessScore.id)
            ]
            return counts, current, history

    before = snapshot()

    client = placement_app["client"]
    headers = placement_app["headers"]["Staff"]
    client.get("/placement/dashboard", headers=headers)
    client.get("/placement/students?page=1&page_size=2", headers=headers)
    client.get(
        f"/placement/students/{placement_app['ids']['Ava CSE']}",
        headers=headers,
    )

    after = snapshot()
    assert after == before


def test_list_rejects_unallowlisted_sort_fields(placement_app: dict) -> None:
    response = placement_app["client"].get(
        "/placement/students?sort_by=email",
        headers=placement_app["headers"]["Admin"],
    )
    assert response.status_code == 422
