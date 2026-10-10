from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.database import Base, get_db
from app.models import AssessmentAttempt, GapReport, LearningCourse, Roadmap, User
from app.routers.premium_router import router as premium_router
from app.routers.learning_router import router as learning_router


@pytest.fixture(autouse=True)
def reset_shared_llm_request_state(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import llm

    monkeypatch.setattr(
        llm,
        "_provider_slots",
        threading.BoundedSemaphore(llm._MAX_CONCURRENT_PROVIDER_REQUESTS),
    )
    monkeypatch.setattr(llm, "_rate_limit_lock", threading.Lock())
    monkeypatch.setattr(llm, "_rate_limited_until", 0.0)


@pytest.fixture
def learning_app(monkeypatch: pytest.MonkeyPatch) -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    with testing_session_local() as db:
        user = User(name="Learner", email="learner@example.test", hashed_password="hash", branch="CSE", semester=4, target_role="Backend Developer")
        another_user = User(name="Other Learner", email="other@example.test", hashed_password="hash", branch="ECE", semester=5)
        db.add_all([user, another_user])
        db.commit()
        db.refresh(user)
        db.refresh(another_user)
        user_id = user.id
        another_user_id = another_user.id

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(learning_router)
    app.include_router(premium_router)
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    data = {
        "client": client,
        "headers": {"Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"},
        "other_headers": {"Authorization": f"Bearer {create_access_token({'sub': str(another_user_id)})}"},
        "session_factory": testing_session_local,
        "user_id": user_id,
        "another_user_id": another_user_id,
    }
    yield data
    client.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def valid_llm_course() -> dict:
    def lesson(title: str) -> dict:
        return {
            "title": title,
            "introduction": "This short introduction explains the concept in a beginner-friendly way.",
            "explanation": "A concept can be understood by starting with its purpose and following one small example step by step.",
            "example": "Use one small example and identify its input and expected result.",
            "code_example": "print('hello')",
            "code_language": "python",
            "example_explanation": "The example shows a small operation and makes its result visible to the learner.",
            "real_world_applications": ["Building a small feature in an application."],
            "common_mistakes": ["Skipping the explanation and copying the example."],
            "key_takeaways": ["Start with a small example."],
            "quick_recap": "Understand the purpose, then trace one small example.",
        }

    return {
        "introduction": "This guide introduces the skill through a few manageable beginner concepts.",
        "learning_objectives": ["Explain the purpose of the skill.", "Follow a small example."],
        "lessons": [lesson("Foundations"), lesson("Applying the concept")],
        "quick_recap": "Start with foundations and connect each concept to an example.",
    }


def test_learning_content_is_validated_and_cached(learning_app: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import learning_content

    calls = []

    def fake_llm(prompt: str, retries: int = 2) -> dict:
        calls.append(prompt)
        return valid_llm_course()

    monkeypatch.setattr(learning_content, "ask_llm_json", fake_llm)
    client = learning_app["client"]
    first = client.get("/learning/skill", params={"skill_id": "Python"}, headers=learning_app["headers"])
    second = client.get("/learning/skill", params={"skill_id": "Python"}, headers=learning_app["headers"])

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["skill_id"] == "Python"
    assert [lesson["lesson_id"] for lesson in first.json()["content"]["lessons"]] == ["lesson-1", "lesson-2"]
    assert first.json()["content_source"] == "llm"
    assert len(calls) == 1
    assert first.json()["context"]["target_role"] == "Backend Developer"
    assert "mastery" in first.json()["completion_notice"].lower()
    assert "mastery" not in first.json()


def test_context_uses_only_available_profile_gap_and_roadmap_data(
    learning_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import learning_content

    prompts = []
    monkeypatch.setattr(
        learning_content,
        "ask_llm_json",
        lambda prompt, retries=2: prompts.append(prompt) or valid_llm_course(),
    )
    with learning_app["session_factory"]() as db:
        db.add(
            GapReport(
                user_id=learning_app["user_id"],
                target_role="Backend Developer",
                covered_by_syllabus=[],
                from_resume=[],
                missing=[{"skill": "Operating Systems", "status": "learn from scratch"}],
                skill_match_pct=0,
            )
        )
        db.add(
            Roadmap(
                user_id=learning_app["user_id"],
                weeks=[
                    {
                        "week": 2,
                        "theme": "Backend foundations",
                        "tasks": [{"task": "[LEARN] Operating Systems - Study processes.", "completed": False}],
                    }
                ],
            )
        )
        db.commit()

    response = learning_app["client"].get(
        "/learning/skill",
        params={"skill_id": "Operating Systems"},
        headers=learning_app["headers"],
    )
    assert response.status_code == 200
    context = response.json()["context"]
    assert context["target_role"] == "Backend Developer"
    assert context["branch"] == "CSE"
    assert context["semester"] == 4
    assert "Operating Systems" in context["vtu_subjects"]
    assert context["gap"] == {"category": "missing", "status": "learn from scratch"}
    assert context["roadmap"]["study_type"] == "learning from scratch"
    assert context["roadmap"]["week"] == 2
    assert "Backend Developer" in prompts[0]


def test_learning_context_does_not_invent_missing_profile_data(
    learning_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import learning_content

    monkeypatch.setattr(learning_content, "ask_llm_json", lambda prompt, retries=2: valid_llm_course())
    response = learning_app["client"].get(
        "/learning/skill",
        params={"skill_id": "Python"},
        headers=learning_app["other_headers"],
    )

    assert response.status_code == 200
    context = response.json()["context"]
    assert context["target_role"] is None
    assert context["branch"] == "ECE"
    assert context["semester"] == 5
    assert context["vtu_subjects"] == []


def test_learning_context_ignores_gap_report_for_another_target_role(
    learning_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import learning_content

    monkeypatch.setattr(learning_content, "ask_llm_json", lambda prompt, retries=2: valid_llm_course())
    with learning_app["session_factory"]() as db:
        db.add(
            GapReport(
                user_id=learning_app["user_id"],
                target_role="Frontend Developer",
                covered_by_syllabus=[],
                from_resume=[],
                missing=[{"skill": "Python", "status": "learn from scratch"}],
                skill_match_pct=0,
            )
        )
        db.commit()

    response = learning_app["client"].get(
        "/learning/skill",
        params={"skill_id": "Python"},
        headers=learning_app["headers"],
    )
    assert response.status_code == 200
    assert response.json()["context"]["target_role"] == "Backend Developer"
    assert response.json()["context"]["gap"] is None


def test_learning_progress_persists_and_is_owned_by_user(learning_app: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import learning_content

    monkeypatch.setattr(learning_content, "ask_llm_json", lambda prompt, retries=2: valid_llm_course())
    client = learning_app["client"]
    course = client.get("/learning/skill", params={"skill_id": "Python"}, headers=learning_app["headers"]).json()
    update = {"skill_id": "Python", "lesson_id": "lesson-1", "completed": True}

    saved = client.put("/learning/progress", json=update, headers=learning_app["headers"])
    assert saved.status_code == 200
    assert saved.json()["completed_lessons"] == ["lesson-1"]
    assert saved.json()["progress"] == {"completed": 1, "total": 2}

    restored = client.get("/learning/skill", params={"skill_id": "Python"}, headers=learning_app["headers"])
    assert restored.json()["completed_lessons"] == ["lesson-1"]
    assert restored.json()["content"] == course["content"]

    other_user_update = client.put("/learning/progress", json=update, headers=learning_app["other_headers"])
    assert other_user_update.status_code == 404
    with learning_app["session_factory"]() as db:
        saved_course = db.query(LearningCourse).filter(LearningCourse.user_id == learning_app["user_id"]).one()
        assert saved_course.completed_lessons == ["lesson-1"]


def test_learning_requires_authentication(learning_app: dict) -> None:
    response = learning_app["client"].get("/learning/skill", params={"skill_id": "Python"})
    assert response.status_code == 401


def test_unknown_and_missing_skill_ids_are_rejected(learning_app: dict) -> None:
    client = learning_app["client"]
    headers = learning_app["headers"]

    unknown = client.get("/learning/skill", params={"skill_id": "PyThn"}, headers=headers)
    missing = client.get("/learning/skill", headers=headers)
    assert unknown.status_code == 404
    assert missing.status_code == 422


def test_llm_failure_uses_structured_fallback(learning_app: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import learning_content

    monkeypatch.setattr(
        learning_content,
        "ask_llm_json",
        lambda prompt, retries=2: {"error": "LLM unavailable"},
    )
    response = learning_app["client"].get(
        "/learning/skill",
        params={"skill_id": "SQL"},
        headers=learning_app["headers"],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["content_source"] == "fallback"
    assert len(body["content"]["lessons"]) == 3
    assert body["content"]["lessons"][0]["code_language"] == "sql"
    assert body["content"]["lessons"][0]["code_example"]


def test_invalid_llm_content_uses_fallback(
    learning_app: dict,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.services import learning_content

    monkeypatch.setattr(learning_content, "ask_llm_json", lambda prompt, retries=2: {"lessons": []})
    response = learning_app["client"].get(
        "/learning/skill",
        params={"skill_id": "Data Structures"},
        headers=learning_app["headers"],
    )

    assert response.status_code == 200
    assert response.json()["content_source"] == "fallback"
    validation_log = next(record for record in caplog.records if record.groq_operation == "lesson_generation")
    assert validation_log.groq_stage == "schema_validation"
    assert validation_log.groq_category == "invalid_response_schema"


def test_invalid_lesson_and_unstarted_course_are_rejected(learning_app: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import learning_content

    monkeypatch.setattr(learning_content, "ask_llm_json", lambda prompt, retries=2: valid_llm_course())
    client = learning_app["client"]
    headers = learning_app["headers"]

    not_started = client.put(
        "/learning/progress",
        json={"skill_id": "Python", "lesson_id": "lesson-1", "completed": True},
        headers=headers,
    )
    assert not_started.status_code == 404

    client.get("/learning/skill", params={"skill_id": "Python"}, headers=headers)
    invalid_lesson = client.put(
        "/learning/progress",
        json={"skill_id": "Python", "lesson_id": "lesson-99", "completed": True},
        headers=headers,
    )
    assert invalid_lesson.status_code == 404


def test_roadmap_mapping_uses_explicit_known_skill_headings(
    learning_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import learning_content
    from app.services.learning_content import map_roadmap_task_skill

    monkeypatch.setattr(learning_content, "ask_llm_json", lambda prompt, retries=2: valid_llm_course())
    assert map_roadmap_task_skill("[LEARN] JavaScript Fundamentals - Study variables.") == "JavaScript"
    assert map_roadmap_task_skill("[REVISE] Python Basics - Review data types.") == "Python"
    assert map_roadmap_task_skill("[LEARN] Unknown Framework Fundamentals - Study tools.") is None

    with learning_app["session_factory"]() as db:
        db.add(
            Roadmap(
                user_id=learning_app["user_id"],
                weeks=[
                    {
                        "week": 1,
                        "theme": "Foundations",
                        "tasks": [
                            {"task": "[REVISE] Data Structures - Review lists.", "completed": False},
                            {"task": "[LEARN] SQL (Weight 3/3) - Learn queries.", "completed": False},
                            {"task": "[LEARN] JavaScript Fundamentals - Study variables.", "completed": False},
                            {"task": "[PRACTICE] Review your project.", "completed": False},
                            {"task": "Legacy task without a skill mapping", "completed": False},
                        ],
                    }
                ],
            )
        )
        db.commit()

    response = learning_app["client"].get("/learning/roadmap-mappings", headers=learning_app["headers"])
    assert response.status_code == 200
    assert response.json()["mappings"] == [
        {"week_index": 0, "task_index": 0, "skill_id": "Data Structures"},
        {"week_index": 0, "task_index": 1, "skill_id": "SQL"},
        {"week_index": 0, "task_index": 2, "skill_id": "JavaScript"},
    ]
    lesson = learning_app["client"].get(
        "/learning/skill",
        params={"skill_id": response.json()["mappings"][2]["skill_id"]},
        headers=learning_app["headers"],
    )
    assert lesson.status_code == 200
    assert lesson.json()["skill_id"] == "JavaScript"


def test_unmapped_legacy_roadmap_returns_empty_mappings(learning_app: dict) -> None:
    with learning_app["session_factory"]() as db:
        db.add(
            Roadmap(
                user_id=learning_app["user_id"],
                weeks=[{"week": 1, "theme": "Legacy", "tasks": [{"task": "Task 1.1", "completed": False}]}],
            )
        )
        db.commit()

    response = learning_app["client"].get("/learning/roadmap-mappings", headers=learning_app["headers"])
    assert response.status_code == 200
    assert response.json() == {"mappings": []}


def test_progress_request_rejects_extra_fields(learning_app: dict) -> None:
    response = learning_app["client"].put(
        "/learning/progress",
        json={
            "skill_id": "Python",
            "lesson_id": "lesson-1",
            "completed": True,
            "mastery_score": 100,
        },
        headers=learning_app["headers"],
    )
    assert response.status_code == 422


def _open_study_coach_course(
    learning_app: dict,
    monkeypatch: pytest.MonkeyPatch,
    skill_id: str = "Python",
    headers: dict | None = None,
) -> dict:
    from app.services import learning_content

    monkeypatch.setattr(learning_content, "ask_llm_json", lambda prompt, retries=2: valid_llm_course())
    response = learning_app["client"].get(
        "/learning/skill",
        params={"skill_id": skill_id},
        headers=headers or learning_app["headers"],
    )
    assert response.status_code == 200
    return response.json()


def _coach_assessment_result(concept: str, count: int = 3) -> dict:
    return {
        "questions": [
            {
                "concept": concept,
                "is_correct": True,
                "answer": "PRIVATE_RAW_ASSESSMENT_ANSWER",
                "correct_answer": "PRIVATE_ASSESSMENT_KEY",
                "explanation": "PRIVATE_ASSESSMENT_EXPLANATION",
            }
            for _ in range(count)
        ]
    }


def test_study_coach_uses_relevant_context_and_returns_validated_actions(
    learning_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import study_coach

    _open_study_coach_course(learning_app, monkeypatch)
    with learning_app["session_factory"]() as db:
        user = db.get(User, learning_app["user_id"])
        user.semester = 6
        for offset in range(2):
            db.add(
                AssessmentAttempt(
                    user_id=user.id,
                    skill_id="Python",
                    lesson_id="lesson-1",
                    questions=[],
                    result=_coach_assessment_result("Foundations"),
                    submitted_at=datetime(2026, 10, 10) - timedelta(days=offset),
                )
            )
        for _ in range(4):
            db.add(
                AssessmentAttempt(
                    user_id=learning_app["another_user_id"],
                    skill_id="Python",
                    lesson_id="lesson-1",
                    questions=[],
                    result=_coach_assessment_result("Foundations"),
                    submitted_at=datetime(2026, 10, 10),
                )
            )
        db.commit()

    captured = {}

    def fake_llm(prompt: str, retries: int = 2, max_tokens: int | None = None) -> dict:
        captured.update(prompt=prompt, retries=retries, max_tokens=max_tokens)
        return {
            "explanation": "A variable gives a name to a value so the program can use it again.",
            "hints": ["First identify the value.", "Then trace where the name is used."],
            "example": "Set a name to a value, then read that name in the next statement.",
        }

    monkeypatch.setattr(study_coach, "ask_llm_json", fake_llm)
    response = learning_app["client"].post(
        "/learning/coach",
        json={
            "skill_id": "Python",
            "lesson_id": "lesson-1",
            "concept": "Foundations",
            "question": "How do I trace a value?",
        },
        headers=learning_app["headers"],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "groq"
    assert body["evidence"]["status"] == "demonstrated_proficiency"
    assert body["evidence"]["assessment_count"] == 2
    assert body["evidence"]["answered_question_count"] == 6
    assert body["evidence"]["score_pct"] == 100.0
    assert body["evidence"]["concept_status"] == "strength"
    assert '"student_context"' not in captured["prompt"]
    assert "CSE" not in captured["prompt"]
    assert "Backend Developer" not in captured["prompt"]
    assert '"semester":6' not in captured["prompt"]
    assert "Artificial Intelligence" in captured["prompt"]
    assert "demonstrated_proficiency" in captured["prompt"]
    assert "PRIVATE_RAW_ASSESSMENT_ANSWER" not in captured["prompt"]
    assert "PRIVATE_ASSESSMENT_KEY" not in captured["prompt"]
    assert "PRIVATE_ASSESSMENT_EXPLANATION" not in captured["prompt"]
    assert "learner@example.test" not in captured["prompt"]
    assert "hashed_password" not in captured["prompt"]
    assert (captured["retries"], captured["max_tokens"]) == (1, 1000)
    assert body["links"]["lesson"] == "/learn?skill=Python&lesson=lesson-1"
    assert body["links"]["practice"] == {
        "method": "POST",
        "href": "/learning/practice",
        "skill_id": "Python",
        "lesson_id": "lesson-1",
    }
    assert body["links"]["assessment"] == {
        "method": "POST",
        "href": "/learning/assessment",
        "skill_id": "Python",
        "lesson_id": "lesson-1",
    }


@pytest.mark.parametrize(
    ("skill_id", "concept", "question", "answer", "hints", "example"),
    [
        (
            "SQL",
            "JOIN",
            "What does an INNER JOIN return?",
            "An INNER JOIN returns rows where the join condition matches in both tables.",
            [],
            "",
        ),
        (
            "Machine Learning",
            "Model evaluation",
            "Compare precision and recall.",
            "Precision measures how many predicted positives are correct; recall measures how many actual positives were found.",
            ["Check which kind of error matters more for your task."],
            "A medical screening may prioritize recall to miss fewer actual cases.",
        ),
        (
            "Cloud",
            "Scaling",
            "Why might horizontal scaling help during a traffic spike?",
            "Horizontal scaling adds more instances to share incoming work, which can increase capacity during a traffic spike.",
            ["Consider whether the workload can be divided across instances."],
            "A service can add application instances behind a load balancer.",
        ),
        (
            "Statistics",
            "Hypothesis testing",
            "What does a p-value mean?",
            "A p-value is the probability, assuming the null hypothesis and model assumptions, of results at least as extreme as those observed.",
            [],
            "",
        ),
        (
            "Operating Systems",
            "Processes",
            "How is a thread different from a process?",
            "A process has its own address space; threads within a process share that process's resources while executing separately.",
            ["Compare what memory each execution unit can share."],
            "Two threads in one process can access the same heap.",
        ),
        (
            "Data Structures",
            "Trees",
            "How does a binary search tree find a value?",
            "Starting at the root, compare the target with the current value and follow the left or right child according to the ordering rule.",
            ["At each node, decide which side could contain the target."],
            "Searching for 8 in a node containing 5 continues into its right subtree.",
        ),
        (
            "Python",
            "Loops",
            "Why does `range(len(items) - 1)` skip the last item?",
            "The stop value in range is exclusive, so subtracting one makes the loop stop before the final index.",
            ["Check the first and last values produced by range."],
            "For three items, range(2) produces indices 0 and 1, but not 2.",
        ),
        (
            "Python",
            "Expressions",
            "What does `print(sum([2, 3]))` display?",
            "It displays 5 because sum adds the list values 2 and 3, and print writes that result.",
            [],
            "",
        ),
    ],
)
def test_study_coach_answers_are_dynamic_across_learning_domains(
    learning_app: dict,
    monkeypatch: pytest.MonkeyPatch,
    skill_id: str,
    concept: str,
    question: str,
    answer: str,
    hints: list[str],
    example: str,
) -> None:
    from app.services import study_coach

    lesson_data = valid_llm_course()["lessons"][0] | {"lesson_id": "lesson-1"}
    lesson = study_coach.LessonContent.model_validate(lesson_data)
    captured = {}

    def fake_llm(prompt: str, retries: int = 2, max_tokens: int | None = None) -> dict:
        captured["prompt"] = prompt
        return {"explanation": answer, "hints": hints, "example": example}

    monkeypatch.setattr(study_coach, "ask_llm_json", fake_llm)
    guidance, source, _ = study_coach.generate_study_coach_guidance(
        skill_id=skill_id,
        lesson=lesson,
        concept=concept,
        question=question,
        vtu_subjects=[],
        mastery={},
    )

    assert source == "groq"
    assert guidance.explanation == answer
    assert guidance.hints == hints
    assert guidance.example == example
    assert question in captured["prompt"]
    assert skill_id in captured["prompt"]
    assert concept in captured["prompt"]
    assert concept not in lesson.title


def test_study_coach_prompt_prioritizes_questions_and_supports_adjacent_topics(
    learning_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import study_coach

    lesson = study_coach.LessonContent.model_validate(
        valid_llm_course()["lessons"][0] | {"lesson_id": "lesson-1"}
    )
    prompts = []
    monkeypatch.setattr(
        study_coach,
        "ask_llm_json",
        lambda prompt, retries=2, max_tokens=None: prompts.append(prompt)
        or {
            "explanation": "This is a concise clarification request: which step or statement are you asking about?",
            "hints": [],
            "example": "",
        },
    )

    guidance, source, _ = study_coach.generate_study_coach_guidance(
        skill_id="Python",
        lesson=lesson,
        concept="Variables",
        question="Why is that?",
        vtu_subjects=[],
        mastery={},
    )

    assert source == "groq"
    assert "directly in the first sentence" in prompts[0]
    assert "even when the lesson does not" in prompts[0]
    assert "cover them" in prompts[0]
    assert "ask one concise clarification" in prompts[0]
    assert '"student_question":"Why is that?"' in prompts[0]
    assert guidance.hints == []
    assert guidance.example == ""


def test_study_coach_allows_short_and_detailed_answers_without_profile_personalization(
    learning_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import study_coach

    lesson = study_coach.LessonContent.model_validate(
        valid_llm_course()["lessons"][0] | {"lesson_id": "lesson-1"}
    )
    responses = iter(
        [
            {"explanation": "A JOIN combines related rows.", "hints": [], "example": ""},
            {
                "explanation": "A JOIN combines rows from related tables. First, identify the matching key. "
                "Then choose the join type based on whether unmatched rows should remain. Finally, check "
                "whether repeated keys produce multiple output rows.",
                "hints": ["Check the matching key.", "Decide how unmatched rows should be handled."],
                "example": "Joining orders to customers by customer_id attaches each matching customer record.",
            },
        ]
    )
    prompts = []
    monkeypatch.setattr(
        study_coach,
        "ask_llm_json",
        lambda prompt, retries=2, max_tokens=None: prompts.append(prompt) or next(responses),
    )

    concise, _, _ = study_coach.generate_study_coach_guidance(
        "SQL", lesson, "JOIN", "Define JOIN.", [], {}
    )
    detailed, _, _ = study_coach.generate_study_coach_guidance(
        "SQL", lesson, "JOIN", "Explain step by step how to choose a JOIN type.", [], {}
    )

    assert len(concise.explanation) < len(detailed.explanation)
    assert "Define JOIN." in prompts[0]
    assert "step by step" in prompts[1]
    assert all("Backend Developer" not in prompt and '"branch"' not in prompt for prompt in prompts)


@pytest.mark.parametrize("attempt_count", [0, 1])
def test_study_coach_marks_missing_or_insufficient_evidence_without_claiming_failure(
    learning_app: dict,
    monkeypatch: pytest.MonkeyPatch,
    attempt_count: int,
) -> None:
    from app.services import study_coach

    _open_study_coach_course(learning_app, monkeypatch)
    if attempt_count:
        with learning_app["session_factory"]() as db:
            db.add(
                AssessmentAttempt(
                    user_id=learning_app["user_id"],
                    skill_id="Python",
                    lesson_id="lesson-1",
                    questions=[],
                    result=_coach_assessment_result("Foundations"),
                    submitted_at=datetime(2026, 10, 10),
                )
            )
            db.commit()

    captured = []
    monkeypatch.setattr(
        study_coach,
        "ask_llm_json",
        lambda prompt, retries=2, max_tokens=None: captured.append(prompt)
        or {
            "explanation": "A variable gives a name to a value so the program can use it again.",
            "hints": ["First identify the value.", "Then trace where the name is used."],
            "example": "Set a name to a value, then read that name in the next statement.",
        },
    )
    response = learning_app["client"].post(
        "/learning/coach",
        json={"skill_id": "Python", "lesson_id": "lesson-1", "concept": "Foundations"},
        headers=learning_app["headers"],
    )

    evidence = response.json()["evidence"]
    assert response.status_code == 200
    assert evidence["status"] == "insufficient_evidence"
    assert evidence["assessment_count"] == attempt_count
    assert evidence["score_pct"] is None
    assert "not a failure" in evidence["note"]
    assert "insufficient_evidence" in captured[0]


@pytest.mark.parametrize(
    "provider_response",
    [
        {"error": "private provider error"},
        {
            "explanation": "",
            "hints": ["First hint is long enough.", "Second hint is also long enough."],
            "example": "A sufficiently long example is present.",
        },
        {
            "explanation": "A variable gives a name to a value so the program can use it again.",
            "hints": ["First identify the value.", "Then trace where the name is used."],
            "example": "Set a name to a value, then read that name in the next statement.",
            "extra": "not allowed",
        },
        {
            "explanation": "A" * 2601,
            "hints": ["First identify the value.", "Then trace where the name is used."],
            "example": "Set a name to a value, then read that name in the next statement.",
        },
    ],
)
def test_study_coach_uses_lesson_grounded_fallback_for_failed_or_invalid_groq_output(
    learning_app: dict,
    monkeypatch: pytest.MonkeyPatch,
    provider_response: dict,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.services import study_coach

    course = _open_study_coach_course(learning_app, monkeypatch)
    stored_lesson = course["content"]["lessons"][0]
    monkeypatch.setattr(
        study_coach,
        "ask_llm_json",
        lambda prompt, retries=2, max_tokens=None: provider_response,
    )

    response = learning_app["client"].post(
        "/learning/coach",
        json={"skill_id": "Python", "lesson_id": "lesson-1", "concept": "Foundations"},
        headers=learning_app["headers"],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "lesson_fallback"
    assert body["explanation"] == stored_lesson["explanation"]
    assert stored_lesson["example"] in body["example"]
    assert len(body["hints"]) >= 2
    assert "private provider error" not in response.text
    if "error" not in provider_response:
        validation_log = next(record for record in caplog.records if record.groq_operation == "study_coach")
        assert validation_log.groq_stage == "schema_validation"
        assert validation_log.groq_category == "invalid_response_schema"


def test_study_coach_requires_authentication_and_scopes_courses_to_the_student(
    learning_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import study_coach

    _open_study_coach_course(learning_app, monkeypatch)
    calls = []
    monkeypatch.setattr(
        study_coach,
        "ask_llm_json",
        lambda prompt, retries=2, max_tokens=None: calls.append(prompt) or {},
    )
    payload = {"skill_id": "Python", "lesson_id": "lesson-1", "concept": "Foundations"}

    unauthenticated = learning_app["client"].post("/learning/coach", json=payload)
    other_student = learning_app["client"].post(
        "/learning/coach",
        json=payload,
        headers=learning_app["other_headers"],
    )

    assert unauthenticated.status_code == 401
    assert other_student.status_code == 404
    assert calls == []


def test_study_coach_rejects_unknown_skills_invalid_lessons_and_oversized_inputs(
    learning_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open_study_coach_course(learning_app, monkeypatch)
    headers = learning_app["headers"]
    client = learning_app["client"]

    unknown_skill = client.post(
        "/learning/coach",
        json={"skill_id": "Unknown skill", "lesson_id": "lesson-1", "concept": "Foundations"},
        headers=headers,
    )
    invalid_lesson = client.post(
        "/learning/coach",
        json={"skill_id": "Python", "lesson_id": "lesson-99", "concept": "Foundations"},
        headers=headers,
    )
    oversized_concept = client.post(
        "/learning/coach",
        json={"skill_id": "Python", "lesson_id": "lesson-1", "concept": "x" * 121},
        headers=headers,
    )
    oversized_question = client.post(
        "/learning/coach",
        json={
            "skill_id": "Python",
            "lesson_id": "lesson-1",
            "concept": "Foundations",
            "question": "x" * 501,
        },
        headers=headers,
    )
    extra_profile_claim = client.post(
        "/learning/coach",
        json={
            "skill_id": "Python",
            "lesson_id": "lesson-1",
            "concept": "Foundations",
            "mastery_score": 100,
        },
        headers=headers,
    )

    assert unknown_skill.status_code == 404
    assert invalid_lesson.status_code == 404
    assert oversized_concept.status_code == 422
    assert oversized_question.status_code == 422
    assert extra_profile_claim.status_code == 422


def test_study_coach_encodes_the_canonical_skill_in_the_lesson_link(
    learning_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import study_coach

    _open_study_coach_course(learning_app, monkeypatch, skill_id="Operating Systems")
    monkeypatch.setattr(
        study_coach,
        "ask_llm_json",
        lambda prompt, retries=2, max_tokens=None: {
            "explanation": "A process is a running program with its own execution state.",
            "hints": ["Start by identifying the running program.", "Then trace its execution state."],
            "example": "Compare a saved program file with the running process created from it.",
        },
    )
    response = learning_app["client"].post(
        "/learning/coach",
        json={
            "skill_id": "Operating Systems",
            "lesson_id": "lesson-1",
            "concept": "Processes",
        },
        headers=learning_app["headers"],
    )

    assert response.status_code == 200
    assert response.json()["links"]["lesson"] == (
        "/learn?skill=Operating%20Systems&lesson=lesson-1"
    )


def test_llm_wrapper_applies_the_interactive_token_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from app.services import llm

    captured = {}

    def fake_create(**options: object) -> object:
        captured.update(options)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))]
        )

    monkeypatch.setattr(llm, "_get_model", lambda: "test-model")
    monkeypatch.setattr(
        llm,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
    )

    assert llm.ask_llm_json("Return a small object", retries=1, max_tokens=1000) == {"ok": True}
    assert captured["max_tokens"] == 1000


@pytest.mark.parametrize(
    ("status_code", "category", "expected_attempts"),
    [
        (400, "provider_bad_request", 1),
        (401, "authentication", 1),
        (404, "model_unavailable", 1),
        (429, "rate_limit_exceeded", 2),
        (None, "provider_error", 1),
    ],
)
def test_llm_wrapper_logs_safe_provider_failure_categories(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    status_code: int | None,
    category: str,
    expected_attempts: int,
) -> None:
    from types import SimpleNamespace

    from app.services import llm

    class ProviderFailure(Exception):
        pass

    def fail_model_list() -> object:
        error = ProviderFailure("sensitive-provider-detail-and-secret")
        error.status_code = status_code
        raise error

    monkeypatch.setattr(
        llm,
        "client",
        SimpleNamespace(models=SimpleNamespace(list=fail_model_list)),
    )
    caplog.set_level("WARNING", logger=llm.__name__)

    result = llm.ask_llm_json("sensitive prompt", retries=2)

    assert "error" in result
    records = [record for record in caplog.records if record.name == llm.__name__]
    assert len(records) == expected_attempts
    assert all(record.groq_stage == "model_discovery" for record in records)
    assert all(record.groq_category == category for record in records)
    assert all(record.groq_attempt == index for index, record in enumerate(records, 1))
    assert "sensitive-provider-detail-and-secret" not in caplog.text
    assert "sensitive prompt" not in caplog.text


def test_llm_wrapper_logs_malformed_json_after_repair_fails(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from types import SimpleNamespace

    from app.services import llm

    calls = []

    def fake_create(**options: object) -> object:
        calls.append(options)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="not json <private-response>"))]
        )

    monkeypatch.setattr(llm, "_get_model", lambda: "test-model")
    monkeypatch.setattr(
        llm,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
    )
    caplog.set_level("WARNING", logger=llm.__name__)

    result = llm.ask_llm_json("private prompt", retries=2)

    assert "JSON decode failed" in result["error"]
    assert len(calls) == 2
    records = [record for record in caplog.records if record.name == llm.__name__]
    assert len(records) == 2
    assert all(record.groq_stage == "response_parse" for record in records)
    assert all(record.groq_category == "malformed_json" for record in records)
    assert "<private-response>" not in caplog.text
    assert "private prompt" not in caplog.text


def test_llm_wrapper_respects_short_retry_after_and_records_safe_provider_metadata(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from types import SimpleNamespace

    from app.services import llm

    calls = []
    waits = []

    class RateLimited(Exception):
        status_code = 429
        response = SimpleNamespace(headers={"retry-after": "2"})

    def fake_create(**options: object) -> object:
        calls.append(options)
        if len(calls) == 1:
            raise RateLimited("private provider details")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))]
        )

    monkeypatch.setattr(llm, "_get_model", lambda: "test-model")
    monkeypatch.setattr(llm.time, "sleep", waits.append)
    monkeypatch.setattr(
        llm,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
    )
    caplog.set_level("WARNING", logger=llm.__name__)

    result = llm.ask_llm_json("private prompt", retries=2, max_tokens=1200)

    assert result == {"ok": True}
    assert waits == [2.0]
    assert len(calls) == 2
    assert all(call["response_format"] == {"type": "json_object"} for call in calls)
    assert all(call["max_tokens"] == 1200 for call in calls)
    record = next(record for record in caplog.records if record.name == llm.__name__)
    assert record.groq_stage == "completion"
    assert record.groq_category == "rate_limit_exceeded"
    assert record.groq_status_code == 429
    assert record.groq_model == "test-model"
    assert record.groq_response_format == "json_object"
    assert "private provider details" not in caplog.text
    assert "private prompt" not in caplog.text


def test_llm_wrapper_does_not_retry_before_long_provider_retry_after(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from types import SimpleNamespace

    from app.services import llm

    class RateLimited(Exception):
        status_code = 429
        response = SimpleNamespace(headers={"retry-after": "45"})

    calls = []

    def fail_completion(**options: object) -> object:
        calls.append(options)
        raise RateLimited("private provider details")

    monkeypatch.setattr(llm, "_get_model", lambda: "test-model")
    monkeypatch.setattr(
        llm,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail_completion))),
    )
    caplog.set_level("WARNING", logger=llm.__name__)

    result = llm.ask_llm_json("private prompt", retries=3)

    assert len(calls) == 1
    assert result["error_category"] == "rate_limit_exceeded"
    assert result["status_code"] == 429
    assert result["retry_after_seconds"] == 45
    assert result["attempts"] == 1
    assert result["model"] == "test-model"
    assert result["response_format"] == "json_object"
    record = next(record for record in caplog.records if record.name == llm.__name__)
    assert record.groq_category == "rate_limit_exceeded"
    assert record.groq_status_code == 429
    assert record.groq_attempt == 1
    assert "private provider details" not in caplog.text
    assert "private prompt" not in caplog.text


def test_llm_wrapper_caps_persistent_rate_limit_attempts_and_uses_jittered_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from app.services import llm

    class RateLimited(Exception):
        status_code = 429
        response = SimpleNamespace(headers={})

    calls = []
    waits = []

    def fail_completion(**options: object) -> object:
        calls.append(options)
        raise RateLimited("private provider detail")

    monkeypatch.setattr(llm, "_get_model", lambda: "test-model")
    monkeypatch.setattr(llm.random, "uniform", lambda low, high: high)
    monkeypatch.setattr(llm.time, "sleep", waits.append)
    monkeypatch.setattr(
        llm,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail_completion))),
    )

    result = llm.ask_llm_json("private prompt", retries=50)

    assert len(calls) == llm._MAX_WRAPPER_ATTEMPTS == 2
    assert waits == [0.75]
    assert result["error_category"] == "rate_limit_exceeded"
    assert result["attempts"] == 2


def test_llm_wrapper_does_not_retry_provider_quota_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from app.services import llm

    class QuotaExceeded(Exception):
        status_code = 429
        body = {"error": {"code": "insufficient_quota"}}

    calls = []

    def fail_completion(**options: object) -> object:
        calls.append(options)
        raise QuotaExceeded("private provider detail")

    monkeypatch.setattr(llm, "_get_model", lambda: "test-model")
    monkeypatch.setattr(
        llm,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail_completion))),
    )

    result = llm.ask_llm_json("private prompt", retries=2)

    assert result["error_category"] == "quota_exceeded"
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("failure", "expected_category"),
    [
        (TimeoutError("private timeout"), "timeout"),
        (ConnectionError("private connection failure"), "network"),
    ],
)
def test_llm_wrapper_retries_transient_failures_with_bounded_backoff(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    expected_category: str,
) -> None:
    from types import SimpleNamespace

    from app.services import llm

    calls = []
    waits = []

    def fail_completion(**options: object) -> object:
        calls.append(options)
        raise failure

    monkeypatch.setattr(llm, "_get_model", lambda: "test-model")
    monkeypatch.setattr(llm.random, "uniform", lambda low, high: 0.0)
    monkeypatch.setattr(llm.time, "sleep", waits.append)
    monkeypatch.setattr(
        llm,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail_completion))),
    )

    result = llm.ask_llm_json("private prompt", retries=2)

    assert result["error_category"] == expected_category
    assert len(calls) == 2
    assert waits == [0.5]


def test_llm_wrapper_uses_provider_reset_headers_as_retry_guidance() -> None:
    from types import SimpleNamespace

    from app.services.llm import _retry_after_seconds

    assert _retry_after_seconds(
        SimpleNamespace(response=SimpleNamespace(headers={"retry-after-ms": "250"}))
    ) == 0.25
    assert _retry_after_seconds(
        SimpleNamespace(response=SimpleNamespace(headers={"x-ratelimit-reset-requests": "3s"}))
    ) == 3.0


def test_configured_groq_client_disables_sdk_retries() -> None:
    from app.services import llm

    assert llm.client.max_retries == 0
    assert llm.client.timeout == 40.0


def test_sequential_ai_features_share_provider_rate_limit_and_recover_after_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from app.services import llm

    now = [100.0]
    waits = []
    calls = []

    class RateLimited(Exception):
        status_code = 429
        response = SimpleNamespace(headers={"retry-after": "7"})

    def fake_create(**options: object) -> object:
        calls.append(options)
        if len(calls) == 1:
            raise RateLimited("private details")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))]
        )

    def fake_sleep(seconds: float) -> None:
        waits.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(llm.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(llm.time, "sleep", fake_sleep)
    monkeypatch.setattr(llm, "_get_model", lambda: "test-model")
    monkeypatch.setattr(
        llm,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
    )

    failed_resume_analysis = llm.ask_llm_json("resume prompt", retries=1)
    next_feature = llm.ask_llm_json("study coach prompt", retries=1)

    assert failed_resume_analysis["error_category"] == "rate_limit_exceeded"
    assert failed_resume_analysis["retry_after_seconds"] == 7
    assert next_feature == {"ok": True}
    assert len(calls) == 2
    assert waits == [7.0]


def test_concurrent_ai_requests_obey_shared_provider_concurrency_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from app.services import llm

    lock = threading.Lock()
    active = 0
    maximum_active = 0

    def fake_create(**options: object) -> object:
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))]
        )

    monkeypatch.setattr(llm, "_get_model", lambda: "test-model")
    monkeypatch.setattr(
        llm,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
    )

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda index: llm.ask_llm_json(f"prompt {index}", retries=1), range(6)))

    assert results == [{"ok": True}] * 6
    assert 1 < maximum_active <= llm._MAX_CONCURRENT_PROVIDER_REQUESTS


def test_shared_rate_limit_rejects_new_feature_requests_until_long_window_expires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from app.services import llm

    now = [200.0]
    calls = []

    class RateLimited(Exception):
        status_code = 429
        response = SimpleNamespace(headers={"retry-after": "45"})

    def fail_completion(**options: object) -> object:
        calls.append(options)
        raise RateLimited("private details")

    monkeypatch.setattr(llm.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(llm, "_get_model", lambda: "test-model")
    monkeypatch.setattr(
        llm,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail_completion))),
    )

    first = llm.ask_llm_json("interview prompt", retries=2)
    second = llm.ask_llm_json("roadmap prompt", retries=2)

    assert first["error_category"] == "rate_limit_exceeded"
    assert second["error_category"] == "rate_limit_exceeded"
    assert second["retry_after_seconds"] == 45
    assert second["attempts"] == 0
    assert len(calls) == 1


def test_shared_provider_gate_releases_after_timeout_for_next_feature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from app.services import llm

    calls = []

    def fake_create(**options: object) -> object:
        calls.append(options)
        if len(calls) == 1:
            raise TimeoutError("private timeout")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))]
        )

    monkeypatch.setattr(llm, "_get_model", lambda: "test-model")
    monkeypatch.setattr(llm.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        llm,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))),
    )

    first = llm.ask_llm_json("assessment prompt", retries=1)
    second = llm.ask_llm_json("practice prompt", retries=1)

    assert first["error_category"] == "timeout"
    assert second == {"ok": True}
    assert len(calls) == 2


def test_resume_upload_offloads_analysis_and_exposes_safe_provider_retry_delay(
    learning_app: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.routers import resume_router

    thread_ids = {}

    def extract_pdf(_contents: bytes) -> str:
        thread_ids["route"] = threading.get_ident()
        return "A parsed resume."

    def rate_limited_analysis(_resume_text: str) -> dict:
        thread_ids["analysis"] = threading.get_ident()
        return {
            "error": "private provider details",
            "error_category": "rate_limit_exceeded",
            "retry_after_seconds": 7,
        }

    learning_app["client"].app.include_router(resume_router.router)
    monkeypatch.setattr(resume_router, "extract_text_from_pdf", extract_pdf)
    monkeypatch.setattr(resume_router, "analyze_resume", rate_limited_analysis)

    response = learning_app["client"].post(
        "/resume/upload",
        files={"file": ("resume.pdf", b"pdf-content", "application/pdf")},
        headers=learning_app["headers"],
    )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "7"
    assert response.json()["detail"] == "Resume analysis is rate-limited. Please wait before retrying."
    assert thread_ids["analysis"] != thread_ids["route"]
    assert "private provider details" not in response.text


def test_llm_wrapper_logs_completion_failures_without_exception_details(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from types import SimpleNamespace

    from app.services import llm

    def fail_completion(**options: object) -> object:
        raise TimeoutError("private timeout detail and secret")

    monkeypatch.setattr(llm, "_get_model", lambda: "test-model")
    monkeypatch.setattr(
        llm,
        "client",
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail_completion))),
    )
    caplog.set_level("WARNING", logger=llm.__name__)

    llm.ask_llm_json("private prompt", retries=1)

    record = next(record for record in caplog.records if record.name == llm.__name__)
    assert record.groq_stage == "completion"
    assert record.groq_category == "timeout"
    assert record.groq_attempt == 1
    assert "private timeout detail and secret" not in caplog.text
    assert "private prompt" not in caplog.text


def test_llm_wrapper_keeps_safe_metadata_for_parsed_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from app.services import llm

    completion = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content='{"technical_questions": []}'))
        ]
    )
    monkeypatch.setattr(llm, "_get_model", lambda: "test-model")
    monkeypatch.setattr(
        llm,
        "client",
        SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **options: completion)
            )
        ),
    )

    result = llm.ask_llm_json("private prompt", retries=2)

    assert result["technical_questions"] == []
    assert result.provider_model == "test-model"
    assert result.attempts == 1
    assert result.response_format == "json_object"
