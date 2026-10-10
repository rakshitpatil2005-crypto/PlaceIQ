from types import SimpleNamespace

from app.services.skill_mastery import build_skill_mastery


def _assessment_attempt(identifier: int, outcomes: list[bool]) -> SimpleNamespace:
    questions = [
        {
            "question_id": f"q{index}",
            "concept": f"Concept {index % 2}",
            "is_correct": correct,
        }
        for index, correct in enumerate(outcomes)
    ]
    score = round(sum(outcomes) / len(outcomes) * 100, 1)
    return SimpleNamespace(
        id=identifier,
        lesson_id=f"lesson-{identifier}",
        created_at=None,
        submitted_at=None,
        result={"questions": questions, "correct": sum(outcomes), "total": len(outcomes), "score_pct": score},
    )


def test_mastery_requires_two_assessments_and_six_answered_questions() -> None:
    one_attempt = build_skill_mastery("Python", [_assessment_attempt(1, [True, True, True])])

    assert one_attempt["status"] == "insufficient_evidence"
    assert one_attempt["score_pct"] is None
    assert one_attempt["evidence_assessments"] == 1
    assert one_attempt["evidence_questions"] == 3
    assert one_attempt["history"][0]["evidence_score_pct"] is None


def test_all_submitted_questions_contribute_equally_and_history_is_chronological() -> None:
    attempts = [
        _assessment_attempt(1, [True, True, True]),
        _assessment_attempt(2, [False, False, False]),
        _assessment_attempt(3, [True, True, True]),
        _assessment_attempt(4, [True, True, True]),
        _assessment_attempt(5, [True, True, True]),
    ]
    mastery = build_skill_mastery("Python", attempts)

    assert mastery["evidence_assessments"] == 5
    assert mastery["evidence_questions"] == 15
    assert mastery["evidence_correct"] == 12
    assert mastery["score_pct"] == 80.0
    assert mastery["latest_assessment_score_pct"] == 100.0
    assert mastery["status"] == "demonstrated_proficiency"
    assert [item["assessment_id"] for item in mastery["history"]] == [1, 2, 3, 4, 5]
    assert [item["evidence_score_pct"] for item in mastery["history"]] == [None, 50.0, 66.7, 75.0, 80.0]
    assert mastery["history"][1]["status"] == "developing"


def test_recent_assessment_floor_prevents_proficiency_despite_high_cumulative_accuracy() -> None:
    attempts = [
        _assessment_attempt(1, [True, True, True]),
        _assessment_attempt(2, [True, True, True]),
        _assessment_attempt(3, [False, False, False]),
    ]
    mastery = build_skill_mastery("Python", attempts)

    assert mastery["score_pct"] == 66.7
    assert mastery["latest_assessment_score_pct"] == 0.0
    assert mastery["status"] == "developing"


def test_concept_strength_requires_repeated_assessment_evidence() -> None:
    one_attempt = build_skill_mastery("Python", [_assessment_attempt(1, [True, True, True])])
    assert all(concept["status"] == "insufficient_evidence" for concept in one_attempt["concepts"])

    repeated = build_skill_mastery(
        "Python",
        [_assessment_attempt(1, [True, True, True]), _assessment_attempt(2, [True, False, True])],
    )
    assert {concept["status"] for concept in repeated["concepts"]} <= {"strength", "review"}
    assert any(concept["status"] == "strength" for concept in repeated["concepts"])
    assert any(concept["status"] == "review" for concept in repeated["concepts"])
