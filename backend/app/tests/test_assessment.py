from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.database import Base, get_db
from app.models import AssessmentAttempt, LearningCourse, User
from app.routers.learning_router import router as learning_router


@pytest.fixture
def assessment_app() -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    lesson = {
        "lesson_id": "lesson-1",
        "title": "Python foundations",
        "introduction": "Learn the purpose and basic structure of Python programs.",
        "explanation": "Python programs use readable statements to process data one step at a time.",
        "example": "Add each value to a running total and return the result.",
        "code_example": "values = [1, 2]\nprint(sum(values))",
        "code_language": "python",
        "example_explanation": "The sum function adds all values and print displays the result.",
        "real_world_applications": [
            "Calculate a total in a data-processing task.",
            "Summarize incoming measurements before displaying a report.",
        ],
        "common_mistakes": ["Copying code without tracing what it does."],
        "key_takeaways": ["Understand what the program should calculate.", "Trace each step using a small example."],
        "quick_recap": "Read the requirement, trace the example, then check its result.",
    }
    with testing_session_local() as db:
        learner = User(name="Assessment Learner", email="assessment@example.test", hashed_password="hash")
        another = User(name="Other Learner", email="assessment-other@example.test", hashed_password="hash")
        db.add_all([learner, another])
        db.commit()
        db.refresh(learner)
        db.refresh(another)
        learner_id, another_id = learner.id, another.id
        db.add(
            LearningCourse(
                user_id=learner_id,
                skill_id="Python",
                content={"introduction": "A learning guide.", "lessons": [lesson]},
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
        "headers": {"Authorization": f"Bearer {create_access_token({'sub': str(learner_id)})}"},
        "other_headers": {"Authorization": f"Bearer {create_access_token({'sub': str(another_id)})}"},
        "session_factory": testing_session_local,
        "user_id": learner_id,
    }
    client.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _start_assessment(client: TestClient, headers: dict) -> dict:
    response = client.post(
        "/learning/assessment",
        json={"skill_id": "Python", "lesson_id": "lesson-1"},
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()


def _stored_correct_answers(assessment_app: dict, assessment_id: int) -> dict[str, str]:
    with assessment_app["session_factory"]() as db:
        attempt = db.query(AssessmentAttempt).filter_by(id=assessment_id).one()
        return {
            question["question_id"]: question["correct_answer"]
            for question in attempt.questions
        }


def test_assessment_generation_hides_answers_until_submission(
    assessment_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import assessment_engine

    monkeypatch.setattr(assessment_engine, "ask_llm_json", lambda prompt, retries=2: {"error": "unavailable"})
    client = assessment_app["client"]
    started = _start_assessment(client, assessment_app["headers"])

    assert started["skill_id"] == "Python"
    assert started["lesson_id"] == "lesson-1"
    assert started["submitted"] is False
    assert started["content_source"] == "fallback"
    assert len(started["questions"]) >= 3
    assert {question["type"] for question in started["questions"]} == {"mcq"}
    for question in started["questions"]:
        assert "correct_answer" not in question
        assert "explanation" not in question
        assert len(question["options"]) == 4
        assert len({option["id"] for option in question["options"]}) == 4
        assert len({option["text"].casefold() for option in question["options"]}) == 4

    retrieved = client.get(
        f"/learning/assessment/{started['id']}",
        headers=assessment_app["headers"],
    )
    assert retrieved.status_code == 200
    assert retrieved.json()["submitted"] is False
    assert "correct_answer" not in retrieved.json()["questions"][0]
    option_sets = []
    for question in started["questions"]:
        options = question["options"]
        assert len(options) == 4
        assert len({option["id"] for option in options}) == 4
        assert len({option["text"].casefold() for option in options}) == 4
        option_sets.append(frozenset(option["text"].casefold() for option in options))
    assert len(set(option_sets)) == len(option_sets)
    assert all(
        len(left.intersection(right)) <= 2
        for index, left in enumerate(option_sets)
        for right in option_sets[index + 1:]
    )
    correct_answers = _stored_correct_answers(assessment_app, started["id"])
    correct_positions = [
        next(
            index
            for index, option in enumerate(question["options"])
            if option["id"] == correct_answers[question["question_id"]]
        )
        for question in started["questions"]
    ]
    assert len(set(correct_positions)) > 1


def test_assessment_submission_persists_score_and_concept_review(
    assessment_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import assessment_engine

    monkeypatch.setattr(assessment_engine, "ask_llm_json", lambda prompt, retries=2: {"error": "unavailable"})
    client = assessment_app["client"]
    started = _start_assessment(client, assessment_app["headers"])
    correct_answers = _stored_correct_answers(assessment_app, started["id"])
    answers = [
        {
            "question_id": question["question_id"],
            "answer": correct_answers[question["question_id"]]
            if index == 0
            else next(
                option["id"]
                for option in question["options"]
                if option["id"] != correct_answers[question["question_id"]]
            ),
        }
        for index, question in enumerate(started["questions"])
    ]
    response = client.post(
        f"/learning/assessment/{started['id']}/submit",
        json={"answers": answers},
        headers=assessment_app["headers"],
    )

    assert response.status_code == 200
    result = response.json()["result"]
    assert response.json()["submitted"] is True
    assert result["correct"] == 1
    assert result["total"] == len(started["questions"])
    assert result["score_pct"] == round(1 / len(started["questions"]) * 100, 1)
    assert any(item["status"] == "strength" for item in result["concepts"])
    assert any(item["status"] == "review" for item in result["concepts"])
    assert all(item["explanation"] and item["correct_answer"] for item in result["questions"])
    assert "not a skill-mastery score" in result["notice"]

    restored = client.get(
        f"/learning/assessment/{started['id']}",
        headers=assessment_app["headers"],
    )
    assert restored.status_code == 200
    assert restored.json()["result"] == result
    assert restored.json()["submitted_answers"] == {item["question_id"]: item["answer"] for item in answers}

    with assessment_app["session_factory"]() as db:
        attempt = db.query(AssessmentAttempt).filter(AssessmentAttempt.user_id == assessment_app["user_id"]).one()
        assert attempt.result["correct"] == 1
        assert attempt.submitted_at is not None


def test_assessment_requires_authentication_and_enforces_ownership(
    assessment_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import assessment_engine

    monkeypatch.setattr(assessment_engine, "ask_llm_json", lambda prompt, retries=2: {"error": "unavailable"})
    client = assessment_app["client"]
    started = _start_assessment(client, assessment_app["headers"])
    assert client.post(
        "/learning/assessment",
        json={"skill_id": "Python", "lesson_id": "lesson-1"},
    ).status_code == 401
    assert client.get(f"/learning/assessment/{started['id']}").status_code == 401
    assert client.get(
        f"/learning/assessment/{started['id']}",
        headers=assessment_app["other_headers"],
    ).status_code == 404
    submitted = client.post(
        f"/learning/assessment/{started['id']}/submit",
        json={"answers": [{"question_id": question["question_id"], "answer": "a"} for question in started["questions"]]},
        headers=assessment_app["other_headers"],
    )
    assert submitted.status_code == 404


def test_assessment_rejects_unknown_skill_lesson_and_incomplete_submission(
    assessment_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import assessment_engine

    monkeypatch.setattr(assessment_engine, "ask_llm_json", lambda prompt, retries=2: {"error": "unavailable"})
    client = assessment_app["client"]
    headers = assessment_app["headers"]
    unknown_skill = client.post(
        "/learning/assessment",
        json={"skill_id": "PyThn", "lesson_id": "lesson-1"},
        headers=headers,
    )
    unknown_lesson = client.post(
        "/learning/assessment",
        json={"skill_id": "Python", "lesson_id": "lesson-unknown"},
        headers=headers,
    )
    assert unknown_skill.status_code == 404
    assert unknown_lesson.status_code == 404

    started = _start_assessment(client, headers)
    incomplete = client.post(
        f"/learning/assessment/{started['id']}/submit",
        json={"answers": [{"question_id": started["questions"][0]["question_id"], "answer": "a"}]},
        headers=headers,
    )
    assert incomplete.status_code == 422
    wrong_id = client.post(
        f"/learning/assessment/{started['id']}/submit",
        json={"answers": [
            {"question_id": f"invalid-{index}", "answer": "a"}
            for index, _ in enumerate(started["questions"])
        ]},
        headers=headers,
    )
    assert wrong_id.status_code == 422


def test_assessment_submission_is_single_use_and_validates_options(
    assessment_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import assessment_engine

    monkeypatch.setattr(assessment_engine, "ask_llm_json", lambda prompt, retries=2: {"error": "unavailable"})
    client = assessment_app["client"]
    headers = assessment_app["headers"]
    started = _start_assessment(client, headers)
    bad_option = client.post(
        f"/learning/assessment/{started['id']}/submit",
        json={"answers": [
            {"question_id": question["question_id"], "answer": "invalid"}
            for question in started["questions"]
        ]},
        headers=headers,
    )
    assert bad_option.status_code == 422
    valid = client.post(
        f"/learning/assessment/{started['id']}/submit",
        json={"answers": [
            {"question_id": question["question_id"], "answer": "a"}
            for question in started["questions"]
        ]},
        headers=headers,
    )
    assert valid.status_code == 200
    duplicate = client.post(
        f"/learning/assessment/{started['id']}/submit",
        json={"answers": [
            {"question_id": question["question_id"], "answer": "a"}
            for question in started["questions"]
        ]},
        headers=headers,
    )
    assert duplicate.status_code == 409


def test_valid_llm_assessment_is_used_and_ids_are_normalized(
    assessment_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import assessment_engine

    question = {
        "question_id": "model-id",
        "concept": "Running totals",
        "type": "mcq",
        "prompt": "Which approach accumulates values into a running total?",
        "options": [
            {"id": "a", "text": "Add each value"},
            {"id": "b", "text": "Replace the total on every iteration"},
            {"id": "c", "text": "Ignore the values"},
            {"id": "d", "text": "Choose a result without tracing"},
        ],
        "code": None,
        "language": None,
        "correct_answer": "a",
        "explanation": "Adding each value keeps the prior partial total.",
    }
    second = {
        **question,
        "question_id": "another-id",
        "concept": "Tracing",
        "prompt": "Which action preserves each intermediate value while tracing?",
        "options": [
            {"id": "a", "text": "Inspect each intermediate value"},
            {"id": "b", "text": "Skip all intermediate values"},
            {"id": "c", "text": "Replace every value without recording it"},
            {"id": "d", "text": "Assume the final value without checking"},
        ],
        "correct_answer": "a",
    }
    third = {
        **question,
        "question_id": "third-id",
        "concept": "Verification",
        "prompt": "Which step verifies the result against the intended calculation?",
        "options": [
            {"id": "a", "text": "Compare the result with the intended calculation"},
            {"id": "b", "text": "Avoid checking the result"},
            {"id": "c", "text": "Change the requirement after calculating"},
            {"id": "d", "text": "Choose an unrelated expected value"},
        ],
        "correct_answer": "a",
        "explanation": "Comparing the result with the intended calculation verifies the expected result.",
    }
    monkeypatch.setattr(
        assessment_engine,
        "ask_llm_json",
        lambda prompt, retries=2: {"questions": [question, second, third]},
    )
    started = _start_assessment(assessment_app["client"], assessment_app["headers"])
    assert started["content_source"] == "llm"
    assert [item["question_id"] for item in started["questions"]] == ["q1", "q2", "q3"]


def test_invalid_llm_assessment_uses_deterministic_fallback(
    assessment_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import assessment_engine

    monkeypatch.setattr(
        assessment_engine,
        "ask_llm_json",
        lambda prompt, retries=2: {"questions": [{"question_id": "q1", "type": "mcq"}]},
    )
    started = _start_assessment(assessment_app["client"], assessment_app["headers"])
    assert started["content_source"] == "fallback"
    assert len(started["questions"]) >= 3
    assert {question["type"] for question in started["questions"]} == {"mcq"}


def test_new_assessment_generation_rejects_code_output_question_type(
    assessment_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import assessment_engine

    invalid_code_output = {
        "question_id": "q1",
        "concept": "Code output",
        "type": "code_output",
        "prompt": "What output does this example produce?",
        "options": [],
        "code": "print(1 + 1)",
        "language": "python",
        "correct_answer": "2",
        "explanation": "The print statement displays the calculated value.",
    }
    monkeypatch.setattr(
        assessment_engine,
        "ask_llm_json",
        lambda prompt, retries=2: {
            "questions": [
                {**invalid_code_output, "question_id": f"q{index}"}
                for index in range(1, 4)
            ]
        },
    )

    started = _start_assessment(assessment_app["client"], assessment_app["headers"])

    assert started["content_source"] == "fallback"
    assert {question["type"] for question in started["questions"]} == {"mcq"}


def test_unusable_ai_code_output_never_replaces_insufficient_mcq_assessment(
    assessment_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models import LearningCourse
    from app.services import assessment_engine

    code_questions = [
        {
            "question_id": f"q{index}",
            "concept": "Code output",
            "type": "code_output",
            "prompt": f"What output does this example produce, question {index}?",
            "options": [],
            "code": "print(1 + 1)",
            "language": "python",
            "correct_answer": "2",
            "explanation": "The print statement displays the calculated value.",
        }
        for index in range(1, 4)
    ]
    monkeypatch.setattr(
        assessment_engine,
        "ask_llm_json",
        lambda prompt, retries=2: {"questions": code_questions},
    )
    with assessment_app["session_factory"]() as db:
        course = db.query(LearningCourse).filter_by(user_id=assessment_app["user_id"]).one()
        course.content = {"lessons": [{"lesson_id": "lesson-1", "title": "An incomplete lesson"}]}
        db.commit()

    response = assessment_app["client"].post(
        "/learning/assessment",
        json={"skill_id": "Python", "lesson_id": "lesson-1"},
        headers=assessment_app["headers"],
    )

    assert response.status_code == 503
    assert "multiple-choice" in response.json()["detail"]
    with assessment_app["session_factory"]() as db:
        assert db.query(AssessmentAttempt).count() == 0


@pytest.mark.parametrize(
    ("skill_id", "concept"),
    [
        ("HTML", "semantic page landmarks"),
        ("C++", "object lifetime and resource cleanup"),
        ("SQL", "matching rows across related tables"),
        ("JavaScript", "promise fulfillment and rejection"),
        ("Machine Learning", "sampling examples to estimate a model"),
    ],
)
def test_assessment_fallback_uses_selected_domain_content(
    skill_id: str,
    concept: str,
) -> None:
    from app.services.assessment_engine import _fallback_questions
    from app.services.question_support import lesson_statements

    lesson = {
        "title": f"{skill_id} concept",
        "introduction": f"This lesson introduces {concept} through a focused example.",
        "explanation": f"The explanation connects {concept} to a specific learning outcome.",
        "example_explanation": f"The example demonstrates how {concept} affects a practical result.",
        "real_world_applications": [f"Use {concept} to evaluate a practical example in context."],
        "key_takeaways": [f"Review how {concept} supports the lesson's main outcome."],
        "common_mistakes": [f"Do not confuse {concept} with an unrelated process."],
        "quick_recap": f"Recall the role of {concept} and verify the example's result.",
    }
    question_set = _fallback_questions(skill_id, lesson)
    source_text = {text for _, text in lesson_statements(lesson)}

    assert len(question_set.questions) >= 3
    for question in question_set.questions:
        assert concept in question.concept
        assert len(question.options) == 4
        assert len({option.text.casefold() for option in question.options}) == 4
        assert question.correct_answer in {option.id for option in question.options}
        assert concept in question.concept
        assert next(option.text for option in question.options if option.id == question.correct_answer) in source_text
        assert next(option.text for option in question.options if option.id == question.correct_answer) in question.explanation
        assert all(option.text in source_text for option in question.options)


def test_assessment_mcq_requires_four_unique_options() -> None:
    from pydantic import ValidationError

    from app.services.assessment_engine import AssessmentQuestion

    question = {
        "question_id": "q1",
        "concept": "Relational joins",
        "type": "mcq",
        "prompt": "Which choice describes matching related rows in the lesson?",
        "options": [
            {"id": "a", "text": "Match rows using the stated relationship"},
            {"id": "b", "text": "Choose a plausible unrelated option"},
            {"id": "c", "text": "Inspect a different lesson concept"},
            {"id": "d", "text": "Ignore the relationship"},
        ],
        "code": None,
        "language": None,
        "correct_answer": "a",
        "explanation": "A join condition identifies rows that satisfy the intended relationship.",
    }
    AssessmentQuestion.model_validate(question)

    with pytest.raises(ValidationError):
        AssessmentQuestion.model_validate({**question, "options": question["options"][:3]})
    duplicate_text = [*question["options"][:3], {"id": "d", "text": " MATCH ROWS USING THE STATED RELATIONSHIP "}]
    with pytest.raises(ValidationError):
        AssessmentQuestion.model_validate({**question, "options": duplicate_text})


def test_persisted_legacy_assessment_mcqs_remain_scorable() -> None:
    from app.services.assessment_engine import score_assessment

    questions = [
        {
            "question_id": f"q{index}",
            "concept": f"Lesson concept {index}",
            "type": "mcq",
            "prompt": f"Which saved option matches the original concept question {index}?",
            "options": [
                {"id": "a", "text": f"Saved correct answer for concept {index}"},
                {"id": "b", "text": f"Saved distractor for concept {index}"},
            ],
            "code": None,
            "language": None,
            "correct_answer": "a",
            "explanation": f"The saved correct answer matches lesson concept {index}.",
        }
        for index in range(1, 4)
    ]

    result = score_assessment(questions, {"q1": "a", "q2": "b", "q3": "a"})

    assert result["correct"] == 2
    assert result["questions"][0]["correct_answer"] == "Saved correct answer for concept 1"


def test_assessment_fallback_returns_recoverable_error_without_sufficient_lesson_content(
    assessment_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import assessment_engine

    monkeypatch.setattr(assessment_engine, "ask_llm_json", lambda prompt, retries=2: {"error": "unavailable"})
    with assessment_app["session_factory"]() as db:
        course = db.query(LearningCourse).filter_by(user_id=assessment_app["user_id"]).one()
        course.content = {"lessons": [{"lesson_id": "lesson-1", "title": "Incomplete lesson"}]}
        db.commit()

    response = assessment_app["client"].post(
        "/learning/assessment",
        json={"skill_id": "Python", "lesson_id": "lesson-1"},
        headers=assessment_app["headers"],
    )
    assert response.status_code == 503
    assert "lesson content" in response.json()["detail"]
    with assessment_app["session_factory"]() as db:
        assert db.query(AssessmentAttempt).count() == 0


def test_code_output_assessment_is_scored_exactly_and_review_uses_readable_choices() -> None:
    from app.services.assessment_engine import score_assessment

    questions = [
        {
            "question_id": "q1",
            "concept": "Loops",
            "type": "code_output",
            "prompt": "What does the code print after processing both values?",
            "options": [],
            "code": "for value in [2, 3]:\n    print(value)",
            "language": "python",
            "correct_answer": "2\n3",
            "explanation": "The loop prints each value on its own line.",
        },
        {
            "question_id": "q2",
            "concept": "Totals",
            "type": "mcq",
            "prompt": "Which action keeps a running total?",
            "options": [
                {"id": "a", "text": "Add each value"},
                {"id": "b", "text": "Replace the total"},
                {"id": "c", "text": "Ignore the values"},
                {"id": "d", "text": "Guess the final result"},
            ],
            "code": None,
            "language": None,
            "correct_answer": "a",
            "explanation": "Adding retains the partial total.",
        },
        {
            "question_id": "q3",
            "concept": "Requirements",
            "type": "mcq",
            "prompt": "What should be identified before solving a problem?",
            "options": [
                {"id": "a", "text": "The desired result"},
                {"id": "b", "text": "A random technique"},
                {"id": "c", "text": "An unrelated example"},
                {"id": "d", "text": "A guess without requirements"},
            ],
            "code": None,
            "language": None,
            "correct_answer": "a",
            "explanation": "The expected result helps guide a solution.",
        },
    ]

    questions[1]["options"].reverse()
    result = score_assessment(questions, {"q1": "2\n3  ", "q2": "b", "q3": "a"})
    assert result["correct"] == 2
    assert result["questions"][0]["is_correct"] is True
    assert result["questions"][1]["answer"] == "Replace the total"
    assert result["questions"][1]["correct_answer"] == "Add each value"
    assert {item["status"] for item in result["concepts"]} == {"strength", "review"}
    reordered_correct = score_assessment(questions, {"q1": "2\n3", "q2": "a", "q3": "a"})
    assert reordered_correct["questions"][1]["is_correct"] is True
    assert reordered_correct["questions"][1]["correct_answer"] == "Add each value"


def test_mastery_api_tracks_submitted_assessment_evidence_and_hides_missing_scores(
    assessment_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models import PracticeAttempt, PracticeSession
    from app.services import assessment_engine

    monkeypatch.setattr(assessment_engine, "ask_llm_json", lambda prompt, retries=2: {"error": "unavailable"})
    client = assessment_app["client"]
    headers = assessment_app["headers"]

    empty = client.get("/learning/mastery", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["skills"] == []

    with assessment_app["session_factory"]() as db:
        practice = PracticeSession(
            user_id=assessment_app["user_id"],
            skill_id="Python",
            lesson_id="lesson-1",
            questions=[],
            content_source="fallback",
        )
        db.add(practice)
        db.commit()
        db.refresh(practice)
        db.add(
            PracticeAttempt(
                user_id=assessment_app["user_id"],
                session_id=practice.id,
                question_id="q1",
                answer="a",
                is_correct=True,
                feedback="Correct.",
                explanation="Practice evidence is not mastery evidence.",
            )
        )
        db.commit()

    still_empty = client.get("/learning/mastery", headers=headers)
    assert still_empty.json()["skills"] == []

    first = _start_assessment(client, headers)
    first_correct_answers = _stored_correct_answers(assessment_app, first["id"])
    first_answers = [
        {"question_id": question["question_id"], "answer": first_correct_answers[question["question_id"]]}
        for question in first["questions"]
    ]
    submitted_first = client.post(
        f"/learning/assessment/{first['id']}/submit",
        json={"answers": first_answers},
        headers=headers,
    )
    assert submitted_first.status_code == 200

    after_one = client.get("/learning/mastery/Python", headers=headers)
    assert after_one.status_code == 200
    assert after_one.json()["status"] == "insufficient_evidence"
    assert after_one.json()["score_pct"] is None
    assert after_one.json()["evidence_assessments"] == 1
    assert after_one.json()["history"][0]["evidence_score_pct"] is None

    second = _start_assessment(client, headers)
    second_correct_answers = _stored_correct_answers(assessment_app, second["id"])
    second_answers = [
        {"question_id": question["question_id"], "answer": second_correct_answers[question["question_id"]]}
        for question in second["questions"]
    ]
    submitted_second = client.post(
        f"/learning/assessment/{second['id']}/submit",
        json={"answers": second_answers},
        headers=headers,
    )
    assert submitted_second.status_code == 200

    overview = client.get("/learning/mastery", headers=headers)
    python_mastery = next(item for item in overview.json()["skills"] if item["skill_id"] == "Python")
    assert python_mastery["status"] == "demonstrated_proficiency"
    assert python_mastery["score_pct"] == 100.0
    assert python_mastery["evidence_assessments"] == 2
    assert len(python_mastery["history"]) == 2
    assert python_mastery["concepts"]
    assert "submitted assessment answers only" in overview.json()["policy"]["evidence"].lower()
    assert python_mastery["assessments"][0]["question_review"][0]["explanation"]


def test_mastery_api_is_authenticated_and_user_scoped(
    assessment_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import assessment_engine

    monkeypatch.setattr(assessment_engine, "ask_llm_json", lambda prompt, retries=2: {"error": "unavailable"})
    client = assessment_app["client"]
    headers = assessment_app["headers"]
    started = _start_assessment(client, headers)
    client.post(
        f"/learning/assessment/{started['id']}/submit",
        json={"answers": [
            {"question_id": question["question_id"], "answer": "a"}
            for question in started["questions"]
        ]},
        headers=headers,
    )

    assert client.get("/learning/mastery").status_code == 401
    assert client.get("/learning/mastery/Python").status_code == 401
    assert client.get("/learning/mastery", headers=assessment_app["other_headers"]).json()["skills"] == []
    other_skill = client.get("/learning/mastery/Python", headers=assessment_app["other_headers"])
    assert other_skill.status_code == 200
    assert other_skill.json()["status"] == "insufficient_evidence"
    assert other_skill.json()["assessments"] == []

    unknown = client.get("/learning/mastery/NotARealSkill", headers=headers)
    assert unknown.status_code == 404
