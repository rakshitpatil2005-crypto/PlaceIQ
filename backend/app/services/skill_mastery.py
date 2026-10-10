from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from app.models import AssessmentAttempt


MINIMUM_ASSESSMENTS = 2
MINIMUM_ANSWERED_QUESTIONS = 6
PROFICIENCY_THRESHOLD = 80.0
RECENT_ASSESSMENT_FLOOR = 70.0
CONCEPT_MINIMUM_ANSWERS = 2
CONCEPT_MINIMUM_ASSESSMENTS = 2
CONCEPT_STRENGTH_THRESHOLD = 80.0

MASTERY_POLICY = {
    "evidence": "Submitted assessment answers only; resume, syllabus, roadmap, lesson completion, practice, and interview data are excluded.",
    "weighting": "Each answered assessment question has equal weight. Every submitted attempt counts once and older attempts are not discarded.",
    "minimum_evidence": (
        f"At least {MINIMUM_ASSESSMENTS} submitted assessments and "
        f"{MINIMUM_ANSWERED_QUESTIONS} answered questions are required before a skill evidence score is shown."
    ),
    "proficiency": (
        f"Demonstrated proficiency requires cumulative accuracy of at least {PROFICIENCY_THRESHOLD:.0f}% "
        f"and accuracy of at least {RECENT_ASSESSMENT_FLOOR:.0f}% on the latest assessment."
    ),
    "concepts": (
        f"Concepts are categorized only after at least {CONCEPT_MINIMUM_ANSWERS} assessment questions "
        f"across {CONCEPT_MINIMUM_ASSESSMENTS} distinct assessments: strength at "
        f"{CONCEPT_STRENGTH_THRESHOLD:.0f}% or better; otherwise review."
    ),
    "practice_and_interviews": "Practice answers and interview feedback are stored separately and do not contribute.",
}


def _status(
    assessment_count: int,
    question_count: int,
    cumulative_score: float,
    latest_score: float,
) -> str:
    if assessment_count < MINIMUM_ASSESSMENTS or question_count < MINIMUM_ANSWERED_QUESTIONS:
        return "insufficient_evidence"
    if cumulative_score >= PROFICIENCY_THRESHOLD and latest_score >= RECENT_ASSESSMENT_FLOOR:
        return "demonstrated_proficiency"
    return "developing"


def _attempt_evidence(attempt: AssessmentAttempt) -> dict:
    result = attempt.result or {}
    questions = result.get("questions", [])
    correct = sum(1 for question in questions if question.get("is_correct") is True)
    total = len(questions)
    return {
        "assessment_id": attempt.id,
        "lesson_id": attempt.lesson_id,
        "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
        "correct": correct,
        "total": total,
        "score_pct": round(correct / total * 100, 1) if total else None,
        "concepts": [
            {
                "concept": question.get("concept"),
                "is_correct": question.get("is_correct") is True,
            }
            for question in questions
            if isinstance(question.get("concept"), str)
        ],
        "question_review": [
            {
                "question_id": question.get("question_id"),
                "concept": question.get("concept"),
                "is_correct": question.get("is_correct") is True,
                "answer": question.get("answer"),
                "correct_answer": question.get("correct_answer"),
                "explanation": question.get("explanation"),
            }
            for question in questions
        ],
    }


def build_skill_mastery(skill_id: str, attempts: list[AssessmentAttempt]) -> dict:
    completed = [attempt for attempt in attempts if attempt.result is not None]
    completed.sort(key=lambda attempt: (attempt.submitted_at or attempt.created_at, attempt.id))

    evidence = []
    cumulative_correct = 0
    cumulative_questions = 0
    history = []
    concept_counts: dict[str, dict] = defaultdict(
        lambda: {"correct": 0, "total": 0, "assessment_ids": set()}
    )

    for attempt in completed:
        item = _attempt_evidence(attempt)
        evidence.append(item)
        cumulative_correct += item["correct"]
        cumulative_questions += item["total"]
        for concept_result in item["concepts"]:
            concept = concept_result["concept"]
            concept_counts[concept]["total"] += 1
            concept_counts[concept]["correct"] += int(concept_result["is_correct"])
            concept_counts[concept]["assessment_ids"].add(attempt.id)

        latest_score = item["score_pct"] if item["score_pct"] is not None else 0.0
        cumulative_score = (
            round(cumulative_correct / cumulative_questions * 100, 1)
            if cumulative_questions
            else 0.0
        )
        status = _status(len(evidence), cumulative_questions, cumulative_score, latest_score)
        history.append(
            {
                "assessment_id": item["assessment_id"],
                "submitted_at": item["submitted_at"],
                "assessment_score_pct": item["score_pct"],
                "assessment_correct": item["correct"],
                "assessment_questions": item["total"],
                "evidence_assessments": len(evidence),
                "evidence_questions": cumulative_questions,
                "evidence_correct": cumulative_correct,
                "evidence_score_pct": cumulative_score if status != "insufficient_evidence" else None,
                "status": status,
            }
        )

    latest = history[-1] if history else None
    concepts = []
    for concept, counts in sorted(concept_counts.items()):
        total = counts["total"]
        assessment_count = len(counts["assessment_ids"])
        score = round(counts["correct"] / total * 100, 1) if total else None
        if total < CONCEPT_MINIMUM_ANSWERS or assessment_count < CONCEPT_MINIMUM_ASSESSMENTS:
            status = "insufficient_evidence"
        elif score is not None and score >= CONCEPT_STRENGTH_THRESHOLD:
            status = "strength"
        else:
            status = "review"
        concepts.append(
            {
                "concept": concept,
                "correct": counts["correct"],
                "total": total,
                "evidence_assessments": assessment_count,
                "score_pct": score if status != "insufficient_evidence" else None,
                "status": status,
            }
        )

    return {
        "skill_id": skill_id,
        "status": latest["status"] if latest else "insufficient_evidence",
        "score_pct": latest["evidence_score_pct"] if latest else None,
        "evidence_assessments": len(evidence),
        "evidence_questions": cumulative_questions,
        "evidence_correct": cumulative_correct,
        "latest_assessment_score_pct": latest["assessment_score_pct"] if latest else None,
        "latest_assessment_id": latest["assessment_id"] if latest else None,
        "concepts": concepts,
        "history": history,
        "assessments": evidence,
        "policy": MASTERY_POLICY,
    }


def get_student_mastery(db: Session, user_id: int) -> list[dict]:
    attempts = (
        db.query(AssessmentAttempt)
        .filter(
            AssessmentAttempt.user_id == user_id,
            AssessmentAttempt.result.is_not(None),
        )
        .order_by(AssessmentAttempt.submitted_at.asc(), AssessmentAttempt.id.asc())
        .all()
    )
    skills: dict[str, list[AssessmentAttempt]] = defaultdict(list)
    for attempt in attempts:
        skills[attempt.skill_id].append(attempt)
    return [build_skill_mastery(skill_id, skills[skill_id]) for skill_id in sorted(skills)]


def get_skill_mastery(db: Session, user_id: int, skill_id: str) -> dict:
    attempts = (
        db.query(AssessmentAttempt)
        .filter(
            AssessmentAttempt.user_id == user_id,
            AssessmentAttempt.skill_id == skill_id,
            AssessmentAttempt.result.is_not(None),
        )
        .order_by(AssessmentAttempt.submitted_at.asc(), AssessmentAttempt.id.asc())
        .all()
    )
    return build_skill_mastery(skill_id, attempts)
