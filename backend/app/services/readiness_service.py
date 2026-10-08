from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import InterviewSession, GapReport, ReadinessScore, ReadinessScoreHistory, Resume, Roadmap, User


def _get_latest_resume_score(db: Session, user_id: int) -> float:
    latest_resume = (
        db.query(Resume)
        .filter(Resume.user_id == user_id)
        .order_by(Resume.id.desc())
        .first()
    )
    if not latest_resume:
        return 0.0
    try:
        value = float(latest_resume.ats_score or 0)
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(100.0, value))


def _get_latest_skill_score(db: Session, user_id: int) -> float:
    latest_gap = (
        db.query(GapReport)
        .filter(GapReport.user_id == user_id)
        .order_by(GapReport.id.desc())
        .first()
    )
    if not latest_gap:
        return 0.0
    try:
        value = float(latest_gap.skill_match_pct or 0)
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(100.0, value))


def _get_latest_roadmap_progress(db: Session, user_id: int) -> float:
    latest_roadmap = (
        db.query(Roadmap)
        .filter(Roadmap.user_id == user_id)
        .order_by(Roadmap.id.desc())
        .first()
    )
    if not latest_roadmap or not latest_roadmap.weeks:
        return 0.0

    total_tasks = 0
    completed_tasks = 0
    for week in latest_roadmap.weeks or []:
        tasks = week.get("tasks", []) if isinstance(week, dict) else []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            total_tasks += 1
            if task.get("completed"):
                completed_tasks += 1

    if total_tasks == 0:
        return 0.0
    return round((completed_tasks / total_tasks) * 100, 2)


def _get_latest_interview_score(db: Session, user_id: int) -> float:
    latest_session = (
        db.query(InterviewSession)
        .filter(InterviewSession.user_id == user_id)
        .order_by(InterviewSession.id.desc())
        .first()
    )
    if not latest_session:
        return 0.0
    score = latest_session.overall_score
    try:
        value = float(score or 0)
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(100.0, value))


def compute_readiness_metrics(db: Session, user: User) -> dict[str, float]:
    resume_score = _get_latest_resume_score(db, user.id)
    skill_score = _get_latest_skill_score(db, user.id)
    roadmap_score = _get_latest_roadmap_progress(db, user.id)
    interview_score = _get_latest_interview_score(db, user.id)

    total = round(
        (0.25 * resume_score) + (0.30 * skill_score) + (0.15 * roadmap_score) + (0.30 * interview_score),
        2,
    )

    return {
        "resume_score": resume_score,
        "skill_score": skill_score,
        "roadmap_score": roadmap_score,
        "interview_score": interview_score,
        "total": total,
    }


def persist_readiness_score(db: Session, user: User) -> dict[str, Any]:
    metrics = compute_readiness_metrics(db, user)
    current = (
        db.query(ReadinessScore)
        .filter(ReadinessScore.user_id == user.id)
        .order_by(ReadinessScore.id.desc())
        .first()
    )

    if current:
        previous_values = {
            "resume_score": current.resume_score,
            "skill_score": current.skill_score,
            "roadmap_score": current.roadmap_score,
            "interview_score": current.interview_score,
            "total": current.total,
        }
        if previous_values == metrics:
            return {
                "id": current.id,
                **metrics,
                "history_written": False,
            }

        current.resume_score = metrics["resume_score"]
        current.skill_score = metrics["skill_score"]
        current.roadmap_score = metrics["roadmap_score"]
        current.interview_score = metrics["interview_score"]
        current.total = metrics["total"]
        db.commit()
        db.refresh(current)
        history_entry = ReadinessScoreHistory(
            user_id=user.id,
            resume_score=metrics["resume_score"],
            skill_score=metrics["skill_score"],
            roadmap_score=metrics["roadmap_score"],
            interview_score=metrics["interview_score"],
            total=metrics["total"],
        )
        db.add(history_entry)
        db.commit()
        return {
            "id": current.id,
            **metrics,
            "history_written": True,
        }

    record = ReadinessScore(
        user_id=user.id,
        resume_score=metrics["resume_score"],
        skill_score=metrics["skill_score"],
        roadmap_score=metrics["roadmap_score"],
        interview_score=metrics["interview_score"],
        total=metrics["total"],
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    history_entry = ReadinessScoreHistory(
        user_id=user.id,
        resume_score=metrics["resume_score"],
        skill_score=metrics["skill_score"],
        roadmap_score=metrics["roadmap_score"],
        interview_score=metrics["interview_score"],
        total=metrics["total"],
    )
    db.add(history_entry)
    db.commit()

    return {
        "id": record.id,
        **metrics,
        "history_written": True,
    }
