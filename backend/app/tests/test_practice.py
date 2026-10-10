from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.database import Base, get_db
from app.models import LearningCourse, PracticeAttempt, PracticeSession, User
from app.routers.learning_router import router as learning_router


@pytest.fixture
def practice_app() -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    with testing_session_local() as db:
        user = User(name="Learner", email="practice@example.test", hashed_password="hash")
        another_user = User(name="Other", email="practice-other@example.test", hashed_password="hash")
        db.add_all([user, another_user])
        db.commit()
        db.refresh(user)
        db.refresh(another_user)
        user_id, another_user_id = user.id, another_user.id

        db.add(
            LearningCourse(
                user_id=user_id,
                skill_id="Python",
                content={
                    "introduction": "A short learning guide.",
                    "lessons": [
                        {
                            "lesson_id": "lesson-1",
                            "title": "Python foundations",
                            "introduction": "Learn the purpose and basic structure of Python programs.",
                            "explanation": "Python programs use readable statements to process data.",
                            "example_explanation": "A small example makes each processing step visible.",
                            "real_world_applications": ["Readable statements help organize a data-processing task."],
                            "common_mistakes": ["Skipping the requirements can lead to processing the wrong data."],
                            "key_takeaways": [
                                "Readable statements make program behavior easier to inspect.",
                                "Process data in steps that match the intended result.",
                            ],
                            "quick_recap": "Read the task, process the data, and inspect the result.",
                        }
                    ],
                },
                context={"target_role": "Backend Developer"},
                completed_lessons=[],
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
        "headers": {"Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"},
        "other_headers": {"Authorization": f"Bearer {create_access_token({'sub': str(another_user_id)})}"},
        "session_factory": testing_session_local,
        "user_id": user_id,
    }
    client.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _create_session(client: TestClient, headers: dict) -> dict:
    response = client.post(
        "/learning/practice",
        json={"skill_id": "Python", "lesson_id": "lesson-1"},
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()


def test_practice_generation_validates_and_hides_grading_data(
    practice_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import practice_engine

    monkeypatch.setattr(practice_engine, "ask_llm_json", lambda prompt, retries=2: {"error": "unavailable"})
    result = _create_session(practice_app["client"], practice_app["headers"])

    assert result["skill_id"] == "Python"
    assert result["lesson_id"] == "lesson-1"
    assert result["content_source"] == "fallback"
    assert len(result["questions"]) >= 2
    assert {item["type"] for item in result["questions"]} == {"mcq"}
    with practice_app["session_factory"]() as db:
        stored_session = db.query(PracticeSession).filter_by(id=result["id"]).one()
        stored_questions = stored_session.questions
    option_sets = [
        frozenset(option["text"].casefold() for option in question["options"])
        for question in stored_questions
    ]
    assert len(set(option_sets)) == len(stored_questions)
    assert all(
        len(left.intersection(right)) <= 2
        for index, left in enumerate(option_sets)
        for right in option_sets[index + 1:]
    )
    correct_positions = [
        next(index for index, option in enumerate(question["options"]) if option["id"] == question["correct_answer"])
        for question in stored_questions
    ]
    assert len(set(correct_positions)) > 1
    for question in result["questions"]:
        assert len(question["options"]) == 4
        assert len({option["id"] for option in question["options"]}) == 4
        assert len({option["text"].casefold() for option in question["options"]}) == 4
        assert "correct_answer" not in question
        assert "accepted_keywords" not in question
        assert "reference_answer" not in question
        assert "explanation" not in question
    assert all(
        question["correct_answer"] in {option["id"] for option in question["options"]}
        for question in stored_questions
    )


def test_valid_llm_practice_set_is_used_and_question_ids_are_normalized(
    practice_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import practice_engine

    valid_question = {
        "question_id": "model-supplied-id",
        "type": "mcq",
        "prompt": "Which option correctly describes this lesson concept?",
        "options": [
            {"id": "a", "text": "The correct concept"},
            {"id": "b", "text": "An unrelated concept"},
            {"id": "c", "text": "A different lesson topic"},
            {"id": "d", "text": "A plausible but incorrect explanation"},
        ],
        "code": None,
        "language": None,
        "starter_code": None,
        "correct_answer": "a",
        "accepted_keywords": [],
        "explanation": "The first option accurately describes the concept from the lesson.",
        "reference_answer": "The correct concept.",
    }
    second_question = {
        **valid_question,
        "question_id": "also-model-supplied",
        "prompt": "Which option should you use to apply the lesson concept?",
        "options": [
            {"id": "a", "text": "Use the concept after checking the requirement"},
            {"id": "b", "text": "Guess before identifying the requirement"},
            {"id": "c", "text": "Ignore the lesson example"},
            {"id": "d", "text": "Apply an unrelated concept"},
        ],
    }
    monkeypatch.setattr(
        practice_engine,
        "ask_llm_json",
        lambda prompt, retries=2: {"questions": [valid_question, second_question]},
    )

    result = _create_session(practice_app["client"], practice_app["headers"])
    assert result["content_source"] == "llm"
    assert [question["question_id"] for question in result["questions"]] == ["q1", "q2"]


def test_repeated_llm_options_are_rejected_with_safe_schema_diagnostic(
    practice_app: dict,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.services import practice_engine

    question = {
        "question_id": "q1",
        "type": "mcq",
        "prompt": "Which statement explains the selected lesson concept?",
        "options": [
            {"id": "a", "text": "Use the stated lesson concept."},
            {"id": "b", "text": "Ignore the lesson requirements."},
            {"id": "c", "text": "Choose an unrelated technique."},
            {"id": "d", "text": "Guess without checking the result."},
        ],
        "correct_answer": "a",
        "accepted_keywords": [],
        "explanation": "The first choice directly applies the lesson concept to its stated purpose.",
        "reference_answer": "Apply the lesson concept to the task.",
    }
    second_question = {
        **question,
        "question_id": "q2",
        "prompt": "Which statement identifies the best next step for this concept?",
    }
    monkeypatch.setattr(
        practice_engine,
        "ask_llm_json",
        lambda prompt, retries=2: {"questions": [question, second_question]},
    )
    caplog.set_level("WARNING", logger=practice_engine.__name__)

    result = _create_session(practice_app["client"], practice_app["headers"])

    assert result["content_source"] == "fallback"
    diagnostic = next(record for record in caplog.records if record.name == practice_engine.__name__)
    assert diagnostic.groq_stage == "schema_validation"
    assert diagnostic.groq_category == "invalid_response_schema"
    assert "Apply the lesson concept to the task." not in caplog.text
    assert "Use the stated lesson concept." not in caplog.text


@pytest.mark.parametrize(
    ("skill_id", "concept"),
    [
        ("C++", "object lifetime"),
        ("HTML", "semantic landmarks"),
        ("SQL", "relational joins"),
        ("JavaScript", "promise rejection"),
        ("Statistics", "sampling variability"),
    ],
)
def test_generated_practice_is_concept_specific_across_supported_domains(
    skill_id: str,
    concept: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import practice_engine

    lesson = {
        "title": f"{concept.title()} in {skill_id}",
        "introduction": f"This lesson explains {concept} in {skill_id}.",
        "explanation": f"Understanding {concept} helps apply {skill_id} correctly.",
    }
    generated_questions = []
    for index in range(2):
        correct_text = f"Apply {concept} in {skill_id} example {index + 1}."
        generated_questions.append(
            {
                "question_id": f"model-q{index + 1}",
                "type": "mcq",
                "prompt": f"How does {concept} affect {skill_id} example {index + 1}?",
                "options": [
                    {"id": "a", "text": correct_text},
                    {"id": "b", "text": f"Ignore {concept} in {skill_id} example {index + 1}."},
                    {"id": "c", "text": f"Replace {concept} with another {skill_id} idea {index + 1}."},
                    {"id": "d", "text": f"Guess the result for {concept} in {skill_id} example {index + 1}."},
                ],
                "code": None,
                "language": None,
                "starter_code": None,
                "correct_answer": "a",
                "accepted_keywords": [],
                "explanation": f"The correct choice applies {concept} in {skill_id} example {index + 1}.",
                "reference_answer": correct_text,
            }
        )
    monkeypatch.setattr(
        practice_engine,
        "ask_llm_json",
        lambda prompt, retries=2: {"questions": generated_questions},
    )

    question_set, source = practice_engine.generate_practice_set(skill_id, lesson, {})

    assert source == "llm"
    assert len(question_set.questions) == 2
    assert len({
        option.text
        for question in question_set.questions
        for option in question.options
    }) == 8
    for question in question_set.questions:
        correct_option = next(option for option in question.options if option.id == question.correct_answer)
        assert concept in question.prompt
        assert concept in correct_option.text
        assert concept in question.explanation


def test_provider_failure_has_safe_practice_generation_diagnostic(
    practice_app: dict,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.services import practice_engine

    monkeypatch.setattr(
        practice_engine,
        "ask_llm_json",
        lambda prompt, retries=2: {"error": "private provider exception and secret"},
    )
    caplog.set_level("WARNING", logger=practice_engine.__name__)

    result = _create_session(practice_app["client"], practice_app["headers"])

    assert result["content_source"] == "fallback"
    diagnostic = next(record for record in caplog.records if record.name == practice_engine.__name__)
    assert diagnostic.groq_stage == "provider_result"
    assert diagnostic.groq_category == "provider_failure"
    assert "private provider exception and secret" not in caplog.text
    assert "Python foundations" not in caplog.text


def test_malformed_groq_json_has_safe_practice_diagnostic(
    practice_app: dict,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.services import practice_engine

    monkeypatch.setattr(
        practice_engine,
        "ask_llm_json",
        lambda prompt, retries=2: {"error": "JSON decode failed on attempt 2"},
    )
    caplog.set_level("WARNING", logger=practice_engine.__name__)

    result = _create_session(practice_app["client"], practice_app["headers"])

    assert result["content_source"] == "fallback"
    diagnostic = next(record for record in caplog.records if record.name == practice_engine.__name__)
    assert diagnostic.groq_stage == "provider_result"
    assert diagnostic.groq_category == "malformed_json"
    assert "JSON decode failed on attempt 2" not in caplog.text


def test_practice_mcq_requires_four_distinct_options_and_one_matching_answer() -> None:
    from pydantic import ValidationError

    from app.services.practice_engine import PracticeQuestion

    question = {
        "question_id": "q1",
        "type": "mcq",
        "prompt": "Which statement best describes the selected lesson concept?",
        "options": [
            {"id": "a", "text": "The concept applies in this situation."},
            {"id": "b", "text": "This is a plausible alternative."},
            {"id": "c", "text": "This choice describes another idea."},
            {"id": "d", "text": "This is a distinct final choice."},
        ],
        "correct_answer": "a",
        "accepted_keywords": [],
        "explanation": "The first option accurately describes the selected lesson concept.",
        "reference_answer": "The concept applies in this situation.",
    }
    PracticeQuestion.model_validate(question)

    with pytest.raises(ValidationError):
        PracticeQuestion.model_validate({**question, "options": question["options"][:2]})
    duplicate_text = [*question["options"][:3], {"id": "d", "text": " THE CONCEPT APPLIES IN THIS SITUATION. "}]
    with pytest.raises(ValidationError):
        PracticeQuestion.model_validate({**question, "options": duplicate_text})
    with pytest.raises(ValidationError):
        PracticeQuestion.model_validate({**question, "correct_answer": "missing"})


def test_persisted_legacy_practice_mcq_remains_readable_and_gradable(
    practice_app: dict,
) -> None:
    from app.models import PracticeSession

    legacy_question = {
        "question_id": "q1",
        "type": "mcq",
        "prompt": "Which option matches this previously saved lesson question?",
        "options": [{"id": "a", "text": "The saved correct choice"}, {"id": "b", "text": "The saved distractor"}],
        "code": None,
        "language": None,
        "starter_code": None,
        "correct_answer": "a",
        "accepted_keywords": [],
        "explanation": "The saved correct choice matches the original question's grading key.",
        "reference_answer": "The saved correct choice.",
    }
    with practice_app["session_factory"]() as db:
        saved = PracticeSession(
            user_id=practice_app["user_id"],
            skill_id="Python",
            lesson_id="lesson-1",
            questions=[legacy_question],
            content_source="llm",
        )
        db.add(saved)
        db.commit()
        db.refresh(saved)
        session_id = saved.id

    client = practice_app["client"]
    retrieved = client.get(
        f"/learning/practice/{session_id}",
        headers=practice_app["headers"],
    )
    assert retrieved.status_code == 200
    assert len(retrieved.json()["questions"][0]["options"]) == 2
    assert "correct_answer" not in retrieved.json()["questions"][0]

    graded = client.post(
        f"/learning/practice/{session_id}/answers",
        json={"question_id": "q1", "answer": "a"},
        headers=practice_app["headers"],
    )
    assert graded.status_code == 200
    assert graded.json()["is_correct"] is True


@pytest.mark.parametrize(
    ("skill_id", "title", "introduction", "explanation"),
    [
        ("HTML", "Semantic elements", "HTML elements describe the meaning of page content.", "Semantic landmarks help users navigate a document."),
        ("C++", "Object lifetime", "C++ objects have lifetimes tied to their storage duration.", "Destructors release resources when an object lifetime ends."),
        ("SQL", "Relational joins", "SQL joins combine rows that satisfy a relationship.", "A join condition identifies matching records across tables."),
        ("JavaScript", "Asynchronous promises", "JavaScript promises represent results available in the future.", "Promise handlers process fulfillment or rejection."),
        ("Statistics", "Sampling distributions", "A sampling distribution describes a statistic across repeated samples.", "Its spread helps quantify sampling variability."),
    ],
)
def test_practice_fallback_uses_selected_lesson_content_across_domains(
    skill_id: str,
    title: str,
    introduction: str,
    explanation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import practice_engine

    lesson = {
        "title": title,
        "introduction": introduction,
        "explanation": explanation,
        "example_explanation": f"The example demonstrates one application of {title} with a concrete result.",
        "real_world_applications": [f"Use {title} when working through a relevant practical task."],
        "common_mistakes": [f"Do not confuse {title} with an unrelated operation."],
        "key_takeaways": [f"Remember the central outcome of this lesson about {title}."],
        "quick_recap": f"Review how the lesson presents {title} and its expected result.",
    }
    monkeypatch.setattr(practice_engine, "ask_llm_json", lambda prompt, retries=2: {"error": "unavailable"})

    question_set, source = practice_engine.generate_practice_set(skill_id, lesson, {})

    assert source == "fallback"
    assert len(question_set.questions) >= 2
    assert {question.type for question in question_set.questions} == {"mcq"}
    lesson_facts = {
        text
        for field in (
            "introduction",
            "explanation",
            "example_explanation",
            "real_world_applications",
            "common_mistakes",
            "key_takeaways",
            "quick_recap",
        )
        for text in ([lesson[field]] if isinstance(lesson[field], str) else lesson[field])
    }
    for question in question_set.questions:
        assert title in question.prompt
        assert len(question.options) == 4
        assert len({option.id for option in question.options}) == 4
        assert len({option.text.casefold() for option in question.options}) == 4
        assert question.correct_answer in {option.id for option in question.options}
        correct_option = next(option for option in question.options if option.id == question.correct_answer)
        assert correct_option.text in lesson_facts
        assert correct_option.text in question.explanation


def test_practice_fallback_returns_recoverable_error_without_lesson_evidence(
    practice_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models import LearningCourse
    from app.services import practice_engine

    monkeypatch.setattr(practice_engine, "ask_llm_json", lambda prompt, retries=2: {"error": "unavailable"})
    with practice_app["session_factory"]() as db:
        course = db.query(LearningCourse).filter_by(user_id=practice_app["user_id"]).one()
        course.content = {"lessons": [{"lesson_id": "lesson-1", "title": "Empty lesson"}]}
        db.commit()

    response = practice_app["client"].post(
        "/learning/practice",
        json={"skill_id": "Python", "lesson_id": "lesson-1"},
        headers=practice_app["headers"],
    )
    assert response.status_code == 503
    assert "lesson content" in response.json()["detail"]
    with practice_app["session_factory"]() as db:
        assert db.query(PracticeSession).count() == 0


def test_unusable_ai_short_answers_never_replace_insufficient_mcq_fallback(
    practice_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models import LearningCourse
    from app.services import practice_engine

    open_questions = [
        {
            "question_id": f"q{index}",
            "type": "short_answer",
            "prompt": f"Explain one fact from this short lesson, question {index}.",
            "options": [],
            "code": None,
            "language": None,
            "starter_code": None,
            "correct_answer": "The lesson fact.",
            "accepted_keywords": ["lesson"],
            "explanation": "The response should explain the fact included in the lesson.",
            "reference_answer": "The lesson fact.",
        }
        for index in range(1, 3)
    ]
    monkeypatch.setattr(
        practice_engine,
        "ask_llm_json",
        lambda prompt, retries=2: {"questions": open_questions},
    )
    with practice_app["session_factory"]() as db:
        course = db.query(LearningCourse).filter_by(user_id=practice_app["user_id"]).one()
        course.content = {
            "lessons": [
                {
                    "lesson_id": "lesson-1",
                    "title": "A short lesson",
                    "introduction": "This lesson has one verifiable introductory fact.",
                    "explanation": "This lesson has one separate explanatory fact.",
                }
            ]
        }
        db.commit()

    response = practice_app["client"].post(
        "/learning/practice",
        json={"skill_id": "Python", "lesson_id": "lesson-1"},
        headers=practice_app["headers"],
    )

    assert response.status_code == 503
    assert "multiple-choice" in response.json()["detail"]
    with practice_app["session_factory"]() as db:
        assert db.query(PracticeSession).count() == 0


def test_practice_answer_is_validated_and_persisted(
    practice_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import practice_engine

    monkeypatch.setattr(practice_engine, "ask_llm_json", lambda prompt, retries=2: {"error": "unavailable"})
    client = practice_app["client"]
    session = _create_session(client, practice_app["headers"])
    session_id = session["id"]

    invalid_choice = client.post(
        f"/learning/practice/{session_id}/answers",
        json={"question_id": "q1", "answer": "   "},
        headers=practice_app["headers"],
    )
    assert invalid_choice.status_code == 422

    with practice_app["session_factory"]() as db:
        stored_session = db.query(PracticeSession).filter_by(id=session_id).one()
        correct_option_id = stored_session.questions[0]["correct_answer"]
        wrong_answer = next(
            option["id"]
            for option in stored_session.questions[0]["options"]
            if option["id"] != correct_option_id
        )
    wrong_answer = client.post(
        f"/learning/practice/{session_id}/answers",
        json={"question_id": "q1", "answer": wrong_answer},
        headers=practice_app["headers"],
    )
    assert wrong_answer.status_code == 200
    assert wrong_answer.json()["is_correct"] is False
    assert wrong_answer.json()["explanation"]

    correct_answer = client.post(
        f"/learning/practice/{session_id}/answers",
        json={"question_id": "q1", "answer": correct_option_id},
        headers=practice_app["headers"],
    )
    assert correct_answer.status_code == 200
    assert correct_answer.json()["is_correct"] is True

    restored = client.get(f"/learning/practice/{session_id}", headers=practice_app["headers"])
    assert restored.status_code == 200
    assert restored.json()["attempts"]["q1"]["answer"] == correct_option_id
    assert restored.json()["attempts"]["q1"]["is_correct"] is True

    with practice_app["session_factory"]() as db:
        attempts = db.query(PracticeAttempt).filter(PracticeAttempt.user_id == practice_app["user_id"]).all()
        assert len(attempts) == 2
        course = db.query(LearningCourse).filter(LearningCourse.user_id == practice_app["user_id"]).one()
        assert course.completed_lessons == []


def test_practice_session_enforces_authentication_and_user_ownership(
    practice_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import practice_engine

    monkeypatch.setattr(practice_engine, "ask_llm_json", lambda prompt, retries=2: {"error": "unavailable"})
    client = practice_app["client"]
    session = _create_session(client, practice_app["headers"])

    assert client.post(
        "/learning/practice",
        json={"skill_id": "Python", "lesson_id": "lesson-1"},
    ).status_code == 401
    assert client.get(f"/learning/practice/{session['id']}").status_code == 401
    assert client.get(
        f"/learning/practice/{session['id']}",
        headers=practice_app["other_headers"],
    ).status_code == 404
    assert client.post(
        f"/learning/practice/{session['id']}/answers",
        json={"question_id": "q1", "answer": "a"},
        headers=practice_app["other_headers"],
    ).status_code == 404


def test_practice_rejects_unknown_skills_lessons_and_questions(practice_app: dict) -> None:
    client = practice_app["client"]
    headers = practice_app["headers"]

    unknown_skill = client.post(
        "/learning/practice",
        json={"skill_id": "PyThn", "lesson_id": "lesson-1"},
        headers=headers,
    )
    unknown_lesson = client.post(
        "/learning/practice",
        json={"skill_id": "Python", "lesson_id": "lesson-404"},
        headers=headers,
    )
    assert unknown_skill.status_code == 404
    assert unknown_lesson.status_code == 404

    session = _create_session(client, headers)
    unknown_question = client.post(
        f"/learning/practice/{session['id']}/answers",
        json={"question_id": "q404", "answer": "anything"},
        headers=headers,
    )
    assert unknown_question.status_code == 404


def test_invalid_generated_questions_use_safe_fallback(
    practice_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import practice_engine

    monkeypatch.setattr(
        practice_engine,
        "ask_llm_json",
        lambda prompt, retries=2: {"questions": [{"question_id": "q1", "type": "mcq"}]},
    )
    result = _create_session(practice_app["client"], practice_app["headers"])
    assert result["content_source"] == "fallback"
    assert len(result["questions"]) >= 3


def test_generated_non_mcq_questions_are_rejected(
    practice_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import practice_engine

    no_keywords = {
        "question_id": "q1",
        "type": "short_answer",
        "prompt": "Describe one useful application of this lesson concept.",
        "options": [],
        "code": None,
        "language": None,
        "starter_code": None,
        "correct_answer": "Apply the concept to a relevant task.",
        "accepted_keywords": [],
        "explanation": "Connect the concept to a specific practical application.",
        "reference_answer": "Identify a relevant task, explain the concept, and describe its intended result.",
    }
    valid_mcq = {
        "question_id": "q2",
        "type": "mcq",
        "prompt": "Which option is the best next step for the described lesson?",
        "options": [
            {"id": "a", "text": "Apply the lesson"},
            {"id": "b", "text": "Guess"},
            {"id": "c", "text": "Ignore the lesson"},
            {"id": "d", "text": "Choose an unrelated result"},
        ],
        "code": None,
        "language": None,
        "starter_code": None,
        "correct_answer": "a",
        "accepted_keywords": [],
        "explanation": "Applying the lesson is the appropriate next step.",
        "reference_answer": "Apply the lesson.",
    }
    monkeypatch.setattr(
        practice_engine,
        "ask_llm_json",
        lambda prompt, retries=2: {"questions": [no_keywords, valid_mcq]},
    )
    result = _create_session(practice_app["client"], practice_app["headers"])
    assert result["content_source"] == "fallback"
    assert {question["type"] for question in result["questions"]} == {"mcq"}


def test_fallback_mcq_grading_is_deterministic_when_llm_is_unavailable(
    practice_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import practice_engine

    monkeypatch.setattr(practice_engine, "ask_llm_json", lambda prompt, retries=2: {"error": "unavailable"})
    client = practice_app["client"]
    session = _create_session(client, practice_app["headers"])
    question = session["questions"][0]
    with practice_app["session_factory"]() as db:
        stored_session = db.query(PracticeSession).filter_by(id=session["id"]).one()
        correct_option_id = stored_session.questions[0]["correct_answer"]

    response = client.post(
        f"/learning/practice/{session['id']}/answers",
        json={
            "question_id": question["question_id"],
            "answer": correct_option_id,
        },
        headers=practice_app["headers"],
    )
    assert response.status_code == 200
    assert response.json()["is_correct"] is True
    assert response.json()["feedback"]


def test_practice_request_rejects_extra_fields_and_blank_answers(
    practice_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import practice_engine

    monkeypatch.setattr(practice_engine, "ask_llm_json", lambda prompt, retries=2: {"error": "unavailable"})
    client = practice_app["client"]
    headers = practice_app["headers"]
    extra_field = client.post(
        "/learning/practice",
        json={"skill_id": "Python", "lesson_id": "lesson-1", "user_id": 123},
        headers=headers,
    )
    assert extra_field.status_code == 422
    session = _create_session(client, headers)
    blank_answer = client.post(
        f"/learning/practice/{session['id']}/answers",
        json={"question_id": "q1", "answer": "   "},
        headers=headers,
    )
    assert blank_answer.status_code == 422
