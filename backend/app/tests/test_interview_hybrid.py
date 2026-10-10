from __future__ import annotations

import json

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
from app.services.question_support import QuestionGenerationUnavailable
from app.services.readiness_service import compute_readiness_metrics

INTERVIEW_DIFFICULTIES = tuple(interview_generator.INTERVIEW_DIFFICULTY_GUIDANCE)
INTERVIEW_FOCUS_CASES = (
    ("recommended", "SQL", "Recommended for me"),
    *(
        (focus_key, focus_label, focus_label)
        for focus_key, focus_label in interview_generator.INTERVIEW_FOCUS_AREAS.items()
    ),
    ("custom:Kubernetes", "Kubernetes", "My own focus: Kubernetes"),
)


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


def _valid_generation_response(skill: str = "SQL") -> dict:
    technical = []
    question_patterns = (
        "Which {skill} approach best preserves correctness in the given scenario?",
        "A feature using {skill} behaves unexpectedly; what should be checked first?",
        "When choosing a {skill} strategy, which trade-off best fits the stated requirement?",
        "How should a developer apply {skill} to make this workflow more reliable?",
        "Which change is the strongest practical use of {skill} for this case?",
    )
    for index in range(5):
        options = [
            {"id": f"option-{index}-a", "text": f"Apply {skill} to meet the stated correctness requirement {index}."},
            {"id": f"option-{index}-b", "text": f"Ignore the {skill} result and assume the missing values are correct {index}."},
            {"id": f"option-{index}-c", "text": f"Disable checks and accept every {skill} result without review {index}."},
            {"id": f"option-{index}-d", "text": f"Replace the {skill} step with an unrelated presentation change {index}."},
        ]
        technical.append(
            {
                "question": question_patterns[index].format(skill=skill),
                "skill": skill,
                "options": options,
                "correct_answer": options[0]["id"],
                "explanation": f"{options[0]['text']} is correct for this scenario.",
            }
        )
    return {
        "technical_questions": technical,
        "hr_questions": [
            {"question": "Describe a time you collaborated on a project."},
            {"question": "How do you adapt when a project requirement changes?"},
            {"question": "What interests you about this role?"},
        ],
    }


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


def test_provider_failure_returns_recoverable_generation_error(monkeypatch):
    monkeypatch.setattr(
        interview_generator,
        "ask_llm_json",
        lambda *args, **kwargs: {"error": "provider unavailable"},
    )
    with pytest.raises(QuestionGenerationUnavailable, match="valid hybrid interview"):
        interview_generator.generate_mock_interview(
            target_role="Data Analyst",
            gap_skills=["SQL", "Statistics"],
            weak_skills=["Data Visualization"],
            projects=[{"name": "Sales Dashboard", "tech": ["SQL"]}],
        )


def test_malformed_ai_mcq_returns_recoverable_generation_error(monkeypatch):
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
    with pytest.raises(QuestionGenerationUnavailable, match="valid hybrid interview"):
        interview_generator.generate_mock_interview("Analyst", ["SQL"], [], [])


def test_truncated_or_unparseable_provider_response_is_logged_as_malformed_json(
    monkeypatch, caplog
):
    monkeypatch.setattr(
        interview_generator,
        "ask_llm_json",
        lambda *args, **kwargs: {"error": "JSON decode failed on attempt 2"},
    )

    with pytest.raises(QuestionGenerationUnavailable):
        interview_generator.generate_mock_interview(
            "Engineer", ["Python"], [], [], difficulty="Advanced"
        )

    assert "category=malformed_json" in caplog.text


def test_duplicate_technical_questions_are_rejected(monkeypatch):
    response = _valid_generation_response()
    response["technical_questions"][1]["question"] = response["technical_questions"][0]["question"]
    monkeypatch.setattr(interview_generator, "ask_llm_json", lambda *args, **kwargs: response)

    with pytest.raises(QuestionGenerationUnavailable):
        interview_generator.generate_mock_interview("Engineer", ["SQL"], [], [])


def test_near_duplicate_technical_questions_are_rejected(monkeypatch):
    response = _valid_generation_response()
    original = response["technical_questions"][0]["question"]
    response["technical_questions"][1]["question"] = original.replace(
        "preserves", "protects"
    )
    monkeypatch.setattr(interview_generator, "ask_llm_json", lambda *args, **kwargs: response)

    with pytest.raises(QuestionGenerationUnavailable) as raised:
        interview_generator.generate_mock_interview("Engineer", ["SQL"], [], [])

    assert raised.value.category == "duplicate_question"


def test_invalid_mcq_output_logs_safe_provider_diagnostics(monkeypatch, caplog):
    from app.services.llm import LLMJSONResponse

    response = LLMJSONResponse(
        {"technical_questions": [], "hr_questions": []},
        model="test-model",
        attempts=2,
    )
    monkeypatch.setattr(interview_generator, "ask_llm_json", lambda *args, **kwargs: response)
    caplog.set_level("WARNING", logger=interview_generator.__name__)

    with pytest.raises(QuestionGenerationUnavailable):
        interview_generator.generate_mock_interview("Engineer", ["SQL"], [], [])

    record = next(record for record in caplog.records if record.name == interview_generator.__name__)
    assert record.interview_generation_stage == "question_count"
    assert record.interview_generation_category == "question_count"
    assert record.interview_provider == "test-model"
    assert record.interview_provider_status is None
    assert record.interview_attempts == 2
    assert record.interview_response_format == "json_object"


def test_validation_failure_category_is_returned_safely_by_api(harness, monkeypatch):
    client, _, ids, _ = harness

    def invalid_questions(**kwargs):
        raise QuestionGenerationUnavailable(
            "private generated content",
            category="duplicate_option_text",
        )

    monkeypatch.setattr(interview_router, "generate_mock_interview", invalid_questions)
    response = client.get("/interview/generate", headers=_headers(ids[0]))

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Generated interview validation failed (duplicate_option_text). Please retry."
    )
    assert "private generated content" not in response.text


def test_valid_mcq_with_paraphrased_concept_explanation_is_accepted(monkeypatch):
    response = _valid_generation_response("CSS Grid")
    response["technical_questions"][0]["options"][0]["text"] = "Use CSS Grid"
    response["technical_questions"][0]["explanation"] = (
        "It provides a two-dimensional layout model suited to dashboard cards."
    )
    monkeypatch.setattr(interview_generator, "ask_llm_json", lambda *args, **kwargs: response)

    result = interview_generator.generate_mock_interview(
        "Frontend Developer", ["CSS"], [], [], difficulty="Beginner", focus_area="recommended"
    )

    question = result["questions"][0]
    assert result["focus_area"] == "Recommended for me"
    assert question["skill"] == "CSS Grid"
    assert question["explanation"] == response["technical_questions"][0]["explanation"]
    assert question["correct_answer"] in {option["id"] for option in question["options"]}


@pytest.mark.parametrize(
    ("mutate", "expected_category"),
    [
        (lambda response: response["technical_questions"].pop(), "question_count"),
        (
            lambda response: response["technical_questions"][0]["options"].__setitem__(
                1, response["technical_questions"][0]["options"][0].copy()
            ),
            "duplicate_option_ids",
        ),
        (
            lambda response: response["technical_questions"][0].update(
                correct_answer="not-an-option"
            ),
            "invalid_correct_answer",
        ),
    ],
)
def test_invalid_provider_output_reports_exact_safe_validation_category(
    monkeypatch, caplog, mutate, expected_category
):
    response = _valid_generation_response()
    mutate(response)
    monkeypatch.setattr(interview_generator, "ask_llm_json", lambda *args, **kwargs: response)
    caplog.set_level("WARNING", logger=interview_generator.__name__)

    with pytest.raises(QuestionGenerationUnavailable) as raised:
        interview_generator.generate_mock_interview("Engineer", ["SQL"], [], [])

    record = next(record for record in caplog.records if record.name == interview_generator.__name__)
    assert raised.value.category == expected_category
    assert record.interview_generation_category == expected_category
    assert record.interview_question_index == (1 if expected_category != "question_count" else None)


@pytest.mark.parametrize(
    ("difficulty", "expected_guidance"),
    [
        ("Beginner", "Test foundations"),
        ("Intermediate", "short scenario"),
        ("Advanced", "multi-step reasoning"),
    ],
)
def test_generation_uses_difficulty_specific_prompt_and_returns_eight_questions(
    monkeypatch, difficulty, expected_guidance
):
    captured = {}

    def valid_response(prompt, **kwargs):
        captured.update(prompt=prompt, kwargs=kwargs)
        return _valid_generation_response()

    monkeypatch.setattr(interview_generator, "ask_llm_json", valid_response)
    result = interview_generator.generate_mock_interview(
        "Backend Developer", ["SQL"], ["Python"], [], difficulty=difficulty
    )

    assert difficulty in captured["prompt"]
    assert expected_guidance in captured["prompt"]
    assert captured["kwargs"]["max_tokens"] == interview_generator.MAX_INTERVIEW_GENERATION_TOKENS
    assert result["difficulty"] == difficulty
    assert len(result["questions"]) == 8
    assert [question["type"] for question in result["questions"]] == [
        "technical_mcq",
    ] * 5 + ["hr"] * 3


@pytest.mark.parametrize("difficulty", INTERVIEW_DIFFICULTIES)
@pytest.mark.parametrize(
    ("focus_area", "question_skill", "expected_focus_label"),
    INTERVIEW_FOCUS_CASES,
)
def test_full_difficulty_focus_matrix_through_authenticated_api(
    harness,
    difficulty,
    focus_area,
    question_skill,
    expected_focus_label,
):
    client, session_factory, ids, monkeypatch = harness
    captured = {}

    def valid_response(prompt, **kwargs):
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return _valid_generation_response(question_skill)

    monkeypatch.setattr(
        interview_router,
        "generate_mock_interview",
        interview_generator.generate_mock_interview,
    )
    monkeypatch.setattr(interview_generator, "ask_llm_json", valid_response)

    response = client.get(
        "/interview/generate",
        headers=_headers(ids[0]),
        params={"difficulty": difficulty, "focus_area": focus_area},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["difficulty"] == difficulty
    assert payload["focus_area"] == expected_focus_label
    assert interview_generator.INTERVIEW_DIFFICULTY_GUIDANCE[difficulty] in captured["prompt"]
    resolved_focus, _ = interview_generator.resolve_interview_focus(focus_area)
    assert json.dumps(resolved_focus) in captured["prompt"]
    assert captured["kwargs"]["max_tokens"] == interview_generator.MAX_INTERVIEW_GENERATION_TOKENS
    assert len(payload["questions"]) == 8
    technical = payload["questions"][:5]
    assert all(item["type"] == "technical_mcq" for item in technical)
    assert all(item["skill"] == question_skill for item in technical)
    for question in technical:
        assert question_skill.casefold() in question["question"].casefold()
        assert len(question["options"]) == 4
        assert len({option["id"] for option in question["options"]}) == 4
        assert len({option["text"].casefold() for option in question["options"]}) == 4
        assert "correct_answer" not in question
    for index, question in enumerate(technical):
        options = {option["text"].casefold() for option in question["options"]}
        for previous in technical[:index]:
            assert len(options.intersection(
                option["text"].casefold() for option in previous["options"]
            )) < 3
    assert all(item["type"] == "hr" for item in payload["questions"][5:])
    assert all("correct_answer" not in item for item in payload["questions"])
    with session_factory() as db:
        saved = db.query(InterviewSession).filter_by(user_id=ids[0]).one()
        assert len(saved.questions) == 8
        for question in saved.questions[:5]:
            assert question.get("correct_answer") in {
                option["id"] for option in question["options"]
            }


@pytest.mark.parametrize(
    ("focus", "expected_prompt_text", "expected_label"),
    [
        ("recommended", "server-verified role", "Recommended for me"),
        ("programming_languages", "Programming Languages", "Programming Languages"),
        ("web_development", "Web Development", "Web Development"),
        ("data_structures_algorithms", "Data Structures & Algorithms", "Data Structures & Algorithms"),
        ("database_sql", "Database & SQL", "Database & SQL"),
        ("core_computer_science", "Core Computer Science", "Core Computer Science"),
        ("ai_machine_learning", "AI & Machine Learning", "AI & Machine Learning"),
        ("cloud_computing", "Cloud Computing", "Cloud Computing"),
        ("full_stack_development", "Full Stack Development", "Full Stack Development"),
        ("custom:Kubernetes", "Kubernetes", "My own focus: Kubernetes"),
    ],
)
def test_each_focus_mode_is_used_by_generation(
    monkeypatch, focus, expected_prompt_text, expected_label
):
    captured = {}

    def valid_response(prompt, **kwargs):
        captured["prompt"] = prompt
        return _valid_generation_response()

    monkeypatch.setattr(interview_generator, "ask_llm_json", valid_response)
    result = interview_generator.generate_mock_interview(
        "Backend Developer", ["SQL"], ["Python"], [], focus_area=focus
    )

    assert expected_prompt_text in captured["prompt"]
    assert result["focus_area"] == expected_label


@pytest.mark.parametrize(
    "invalid_focus",
    ["custom:", "topic\ninjected prompt", "custom:SQL; injected prompt", "a" * 121],
)
def test_custom_focus_rejects_empty_or_unsafe_topics(invalid_focus):
    with pytest.raises(ValueError):
        interview_generator.resolve_interview_focus(invalid_focus)


def test_single_character_custom_focus_is_supported():
    assert interview_generator.resolve_interview_focus("custom:C") == (
        "C",
        "My own focus: C",
    )


def test_recommended_focus_uses_only_server_supplied_skills(monkeypatch):
    captured = {}

    def valid_response(prompt, **kwargs):
        captured["prompt"] = prompt
        return _valid_generation_response()

    monkeypatch.setattr(interview_generator, "ask_llm_json", valid_response)
    interview_generator.generate_mock_interview(
        "Backend Developer",
        ["Server Gap Skill"],
        ["Server Weak Skill"],
        [],
        resume_skills=["Server Resume Skill"],
        focus_area="recommended",
    )

    assert "Server Gap Skill" in captured["prompt"]
    assert "Server Weak Skill" in captured["prompt"]
    assert "Server Resume Skill" in captured["prompt"]
    assert "server-verified role" in captured["prompt"]


def test_recommended_focus_api_passes_authenticated_resume_skills(harness, monkeypatch):
    client, session_factory, ids, _ = harness
    with session_factory() as db:
        resume = db.query(Resume).filter_by(user_id=ids[0]).one()
        resume.extracted_skills = ["SQL", "Resume-Only Skill"]
        db.commit()

    captured = {}

    def valid_response(prompt, **kwargs):
        captured["prompt"] = prompt
        return _valid_generation_response()

    monkeypatch.setattr(interview_generator, "ask_llm_json", valid_response)
    monkeypatch.setattr(
        interview_router,
        "generate_mock_interview",
        interview_generator.generate_mock_interview,
    )

    response = client.get(
        "/interview/generate",
        headers=_headers(ids[0]),
        params={"difficulty": "Beginner", "focus_area": "recommended"},
    )

    assert response.status_code == 200
    assert "Resume-Only Skill" in captured["prompt"]


@pytest.mark.parametrize(
    "bad_question",
    [
        {
            "question": "Question with duplicated options",
            "skill": "SQL",
            "options": [{"id": "a", "text": "same"}] * 4,
            "correct_answer": "a",
            "explanation": "same is correct",
        },
        {
            "question": "Question with a missing answer key",
            "skill": "SQL",
            "options": [
                {"id": "a", "text": "correct SQL method"},
                {"id": "b", "text": "wrong method one"},
                {"id": "c", "text": "wrong method two"},
                {"id": "d", "text": "wrong method three"},
            ],
            "correct_answer": "missing",
            "explanation": "correct SQL method is correct.",
        },
    ],
)
def test_mcq_validation_rejects_invalid_options_and_answer_reference(
    monkeypatch, bad_question
):
    response = _valid_generation_response()
    response["technical_questions"][0] = bad_question
    monkeypatch.setattr(interview_generator, "ask_llm_json", lambda *args, **kwargs: response)

    with pytest.raises(QuestionGenerationUnavailable):
        interview_generator.generate_mock_interview("Engineer", ["SQL"], [], [])


def test_interview_generation_rejects_invalid_custom_focus_and_difficulty(harness):
    client, _, ids, _ = harness
    headers = _headers(ids[0])
    assert client.get(
        "/interview/generate",
        headers=headers,
        params={"focus_area": "custom:SQL; injected prompt"},
    ).status_code == 422
    assert client.get(
        "/interview/generate",
        headers=headers,
        params={"difficulty": "Expert"},
    ).status_code == 422


def test_interview_generation_failure_returns_safe_recoverable_error(harness, monkeypatch):
    client, session_factory, ids, _ = harness

    def unavailable(**kwargs):
        raise QuestionGenerationUnavailable("private failure")

    monkeypatch.setattr(interview_router, "generate_mock_interview", unavailable)

    response = client.get("/interview/generate", headers=_headers(ids[0]))

    assert response.status_code == 503
    assert response.json()["detail"] == "Interview questions are temporarily unavailable. Please retry shortly."
    assert "private failure" not in response.text
    with session_factory() as db:
        assert db.query(InterviewSession).filter_by(user_id=ids[0]).count() == 0


def test_interview_rate_limit_is_actionable_and_does_not_persist_session(harness, monkeypatch):
    client, session_factory, ids, _ = harness

    def rate_limited(**kwargs):
        raise QuestionGenerationUnavailable(
            "private provider failure",
            category="rate_limit_exceeded",
            retry_after_seconds=12,
        )

    monkeypatch.setattr(interview_router, "generate_mock_interview", rate_limited)

    response = client.get("/interview/generate", headers=_headers(ids[0]))

    assert response.status_code == 429
    assert response.headers["retry-after"] == "12"
    assert response.json()["detail"] == (
        "Interview generation is rate-limited. Please wait before retrying."
    )
    assert "private provider failure" not in response.text
    with session_factory() as db:
        assert db.query(InterviewSession).filter_by(user_id=ids[0]).count() == 0


def test_interview_quota_failure_is_distinct_and_preserves_prior_session(harness, monkeypatch):
    client, session_factory, ids, _ = harness
    prior = InterviewSession(
        user_id=ids[0],
        target_role="Backend Developer",
        questions=_question_set(),
        answers=[],
        scores=[],
        weak_skills=[],
        overall_score=0,
    )
    with session_factory() as db:
        db.add(prior)
        db.commit()
        prior_id = prior.id

    def quota_exhausted(**kwargs):
        raise QuestionGenerationUnavailable(
            "private quota detail",
            category="quota_exceeded",
        )

    monkeypatch.setattr(interview_router, "generate_mock_interview", quota_exhausted)
    response = client.get("/interview/generate", headers=_headers(ids[0]))

    assert response.status_code == 429
    assert "quota" in response.json()["detail"].lower()
    assert "private quota detail" not in response.text
    with session_factory() as db:
        sessions = db.query(InterviewSession).filter_by(user_id=ids[0]).all()
        assert len(sessions) == 1
        assert sessions[0].id == prior_id


@pytest.mark.parametrize(
    ("category", "expected_detail"),
    [
        ("provider_bad_request", "provider rejected"),
        ("authentication", "provider configuration"),
        ("model_unavailable", "configured interview model"),
        ("timeout", "timed out"),
        ("network", "could not be reached"),
    ],
)
def test_provider_failure_categories_have_safe_actionable_api_messages(
    harness, monkeypatch, category, expected_detail
):
    client, _, ids, _ = harness

    def unavailable(**kwargs):
        raise QuestionGenerationUnavailable(
            "private provider response",
            category=category,
        )

    monkeypatch.setattr(interview_router, "generate_mock_interview", unavailable)
    response = client.get("/interview/generate", headers=_headers(ids[0]))

    assert response.status_code == 503
    assert expected_detail in response.json()["detail"].lower()
    assert "private provider response" not in response.text
