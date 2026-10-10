from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.database import Base, get_db
from app.models import GapReport, InterviewSession, Resume, User
from app.routers import interview_router
from app.services import interview_evaluator, interview_generator
from app.services.readiness_service import compute_readiness_metrics


def _question_set() -> list[dict]:
    questions = []
    for index in range(5):
        options = [
            {"id": "a", "text": f"Question {index + 1} correct answer"},
            {"id": "b", "text": f"Question {index + 1} plausible distractor one"},
            {"id": "c", "text": f"Question {index + 1} plausible distractor two"},
            {"id": "d", "text": f"Question {index + 1} plausible distractor three"},
        ]
        correct_index = index % 4
        correct = options.pop(0)
        options.insert(correct_index, correct)
        questions.append(
            {
                "question_id": f"q{index + 1}",
                "type": "technical_mcq",
                "skill": f"Skill {index + 1}",
                "question": f"Technical question {index + 1} about skill {index + 1}?",
                "options": options,
                "correct_answer": options[correct_index]["id"],
                "explanation": f"The correct answer is {options[correct_index]['text']}.",
                "code": None,
            }
        )
    questions.extend(
        {
            "question_id": f"q{index + 6}",
            "type": "hr",
            "skill": None,
            "question": f"HR question {index + 1}: describe an honest example.",
            "options": [],
        }
        for index in range(3)
    )
    return questions


@pytest.fixture
def harness(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = session_factory()
    users = [
        User(
            name=f"Interview User {index}",
            email=f"interview{index}@example.test",
            hashed_password="test",
            branch="CSE",
            semester=6,
            target_role="Backend Developer",
        )
        for index in range(2)
    ]
    db.add_all(users)
    db.commit()
    for user in users:
        db.add(
            GapReport(
                user_id=user.id,
                target_role=user.target_role,
                missing=[{"skill": "SQL", "status": "learn from scratch"}],
                covered_by_syllabus=[],
                from_resume=[],
                skill_match_pct=50,
            )
        )
        db.add(
            Resume(
                user_id=user.id,
                filename="resume.pdf",
                extracted_skills=["SQL"],
                projects=[{"name": "Inventory", "tech": ["Python", "SQL"]}],
            )
        )
    db.commit()
    ids = [user.id for user in users]
    db.close()

    def override_db():
        scoped = session_factory()
        try:
            yield scoped
        finally:
            scoped.close()

    def override_user(
        authorization: str | None = Header(default=None),
        scoped: Session = Depends(get_db),
    ):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authentication required")
        try:
            user_id = int(authorization.removeprefix("Bearer "))
        except ValueError as error:
            raise HTTPException(status_code=401, detail="Authentication required") from error
        user = scoped.query(User).filter(User.id == user_id).first()
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        return user

    app = FastAPI()
    app.include_router(interview_router.router)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    monkeypatch.setattr(
        interview_router,
        "generate_mock_interview",
        lambda **kwargs: {
            "questions": _question_set(),
            "difficulty": kwargs["difficulty"],
            "focus_area": kwargs["focus_area"],
            "content_source": "llm",
        },
    )
    client = TestClient(app)
    yield client, session_factory, ids, monkeypatch
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _headers(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_id}"}


def test_generation_count_options_and_answer_key_protection(harness):
    client, session_factory, ids, _ = harness
    response = client.get("/interview/generate", headers=_headers(ids[0]))
    assert response.status_code == 200
    generated = response.json()
    assert len(generated["questions"]) == 8
    technical = generated["questions"][:5]
    assert all(question["type"] == "technical_mcq" for question in technical)
    for question in technical:
        assert len(question["options"]) == 4
        assert len({option["id"] for option in question["options"]}) == 4
        assert len({option["text"].casefold() for option in question["options"]}) == 4
        assert "correct_answer" not in question
    for current_index, question in enumerate(technical):
        current_texts = {option["text"].casefold() for option in question["options"]}
        for previous in technical[:current_index]:
            assert len(current_texts.intersection(
                option["text"].casefold() for option in previous["options"]
            )) < 3
    assert all(question["type"] == "hr" for question in generated["questions"][5:])
    assert all("correct_answer" not in question for question in generated["questions"])

    with session_factory() as db:
        saved = db.query(InterviewSession).filter_by(user_id=ids[0]).one()
        assert all(question.get("correct_answer") for question in saved.questions[:5])

    restored = client.get("/interview/session", headers=_headers(ids[0])).json()
    assert all("correct_answer" not in question for question in restored["questions"])


@pytest.mark.parametrize(
    ("correct_count", "expected_technical_score"),
    [(5, 100.0), (0, 0.0)],
)
def test_deterministic_mcq_scoring_and_equal_component_formula(
    harness, correct_count, expected_technical_score
):
    client, session_factory, ids, monkeypatch = harness
    client.get("/interview/generate", headers=_headers(ids[0]))
    monkeypatch.setattr(
        interview_router,
        "evaluate_candidate_answer",
        lambda **kwargs: {
            "score_out_of_10": 8,
            "strengths": "Relevant and specific.",
            "missing_points": "Outcome detail.",
            "improvements": "Clarify the result.",
            "improvement_suggestions": "Clarify the result.",
            "feedback": "Concise response evaluated with the HR rubric.",
            "ideal_answer": None,
            "evaluation_source": "ai",
        },
    )
    questions = client.get("/interview/session", headers=_headers(ids[0])).json()["questions"]

    for index in range(8):
        if index < 5:
            answer = (
                questions[index]["options"][
                    next(
                        option_index
                        for option_index, option in enumerate(questions[index]["options"])
                        if option["id"] == _question_set()[index]["correct_answer"]
                    )
                ]["id"]
            )
            if index >= correct_count:
                answer = next(
                    option["id"]
                    for option in questions[index]["options"]
                    if option["id"] != answer
                )
        else:
            answer = "I contributed to a team project, and we completed the agreed feature."
        response = client.post(
            "/interview/evaluate",
            headers=_headers(ids[0]),
            json={"question_index": index, "answer": answer},
        )
        assert response.status_code == 200
        if index == 0:
            assert "is_correct" in response.json()
            assert response.json()["question_type"] == "technical_mcq"
    final = response.json()
    assert final["completed"] is True
    assert final["technical_score"] == expected_technical_score
    assert final["hr_score"] == 80
    assert final["overall_score"] == pytest.approx((expected_technical_score * 0.5) + 40)

    with session_factory() as db:
        saved = db.query(InterviewSession).filter_by(user_id=ids[0]).one()
        assert saved.overall_score == final["overall_score"]
        assert len(saved.answers) == len(saved.scores) == 8
        assert saved.scores[0]["is_correct"] == (correct_count > 0)
        latest_gap = db.query(GapReport).filter_by(user_id=ids[0]).one()
        saved_user = db.query(User).filter_by(id=ids[0]).one()
        assert compute_readiness_metrics(db, saved_user)["interview_score"] == final["overall_score"]
        if correct_count == 0:
            assert any(item.get("status") == "weak from interview" for item in latest_gap.missing)
            assert saved.weak_skills
        else:
            assert saved.weak_skills == []


def test_duplicate_submission_and_user_isolation(harness):
    client, session_factory, ids, _ = harness
    client.get("/interview/generate", headers=_headers(ids[0]))
    question = client.get("/interview/session", headers=_headers(ids[0])).json()["questions"][0]
    answer = question["options"][0]["id"]
    payload = {"question_index": 0, "answer": answer}
    assert client.post("/interview/evaluate", headers=_headers(ids[0]), json=payload).status_code == 200
    assert client.post("/interview/evaluate", headers=_headers(ids[0]), json=payload).status_code == 409
    invalid_answer = client.post(
        "/interview/evaluate",
        headers=_headers(ids[0]),
        json={"question_index": 1, "answer": "not-an-option", "question": "Injected question", "target_role": "Injected role"},
    )
    assert invalid_answer.status_code == 400
    assert client.get("/interview/session", headers=_headers(ids[1])).json() == {"session": None}
    with session_factory() as db:
        assert db.query(InterviewSession).filter_by(user_id=ids[1]).count() == 0


def test_authentication_required(harness):
    client, _, _, _ = harness
    assert client.get("/interview/session").status_code == 401


def test_hr_empty_short_and_provider_failure_are_labeled(monkeypatch):
    def provider_failure(*args, **kwargs):
        return {"error": "provider unavailable"}

    monkeypatch.setattr(interview_evaluator, "ask_llm_json", provider_failure)
    blank = interview_evaluator.evaluate_candidate_answer("Tell me about a change.", "", "Engineer")
    concise = interview_evaluator.evaluate_candidate_answer(
        "Tell me about a change.", "I adapted to a new deadline.", "Engineer"
    )
    assert blank["score_out_of_10"] == 0
    assert concise["score_out_of_10"] > 0
    assert blank["evaluation_source"] == concise["evaluation_source"] == "fallback"
    assert "unavailable" in concise["feedback"].lower()
    assert concise["ideal_answer"] is None


def test_hr_ai_rubric_and_concise_answer_acceptance(monkeypatch):
    captured = {}

    def ai_response(prompt, **kwargs):
        captured["prompt"] = prompt
        return {
            "score_out_of_10": 8,
            "strengths": "Direct and relevant.",
            "missing_points": "The result could be clearer.",
            "improvement_suggestions": "Add a concrete outcome.",
            "feedback": "A concise answer can be strong.",
            "model_answer": None,
        }

    monkeypatch.setattr(interview_evaluator, "ask_llm_json", ai_response)
    result = interview_evaluator.evaluate_candidate_answer(
        "What interests you about the role?", "I enjoy solving practical problems.", "Engineer"
    )
    assert result["score_out_of_10"] == 8
    assert result["evaluation_source"] == "ai"
    assert "not response length" in captured["prompt"]
    assert result["ideal_answer"] is None


def test_malformed_hr_evaluation_uses_labeled_fallback(monkeypatch):
    monkeypatch.setattr(
        interview_evaluator,
        "ask_llm_json",
        lambda *args, **kwargs: {"score_out_of_10": "not-a-score"},
    )
    result = interview_evaluator.evaluate_candidate_answer(
        "Describe a time you adapted.", "I changed our project plan and we finished on time.", "Engineer"
    )
    assert result["evaluation_source"] == "fallback"
    assert 0 <= result["score_out_of_10"] <= 10
    assert "unavailable" in result["feedback"].lower()


def test_generator_fallback_produces_valid_five_mcqs_and_three_hr(monkeypatch):
    monkeypatch.setattr(
        interview_generator,
        "ask_llm_json",
        lambda *args, **kwargs: {"error": "provider unavailable"},
    )
    result = interview_generator.generate_mock_interview(
        target_role="Data Analyst",
        gap_skills=["SQL", "Statistics"],
        weak_skills=["Data Visualization"],
        projects=[{"name": "Sales Dashboard", "tech": ["SQL"]}],
    )
    assert result["content_source"] == "fallback"
    assert len(result["questions"]) == 8
    assert all(item["type"] == "technical_mcq" for item in result["questions"][:5])
    assert all(item["type"] == "hr" for item in result["questions"][5:])
    for item in result["questions"][:5]:
        assert len(item["options"]) == 4
        assert len({option["id"] for option in item["options"]}) == 4
        assert len({option["text"].casefold() for option in item["options"]}) == 4
        assert item["correct_answer"] in {option["id"] for option in item["options"]}
        assert item["explanation"]
    assert "SQL" in " ".join(item["skill"] for item in result["questions"][:5])


def test_invalid_ai_mcq_is_rejected_and_falls_back(monkeypatch):
    malformed = {
        "technical_questions": [
            {
                "question": f"Q{index}",
                "skill": "SQL",
                "options": [{"id": "a", "text": "same"}] * 4,
                "correct_answer": "a",
                "explanation": "same is correct",
            }
            for index in range(5)
        ],
        "hr_questions": [{"question": f"HR {index}"} for index in range(3)],
    }
    monkeypatch.setattr(interview_generator, "ask_llm_json", lambda *args, **kwargs: malformed)
    result = interview_generator.generate_mock_interview(
        "Analyst", ["SQL"], [], []
    )
    assert result["content_source"] == "fallback"
    assert all(len(question["options"]) == 4 for question in result["questions"][:5])
