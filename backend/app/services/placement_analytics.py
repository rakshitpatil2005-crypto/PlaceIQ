from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import math
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    GapReport,
    InterviewSession,
    ReadinessScoreHistory,
    Resume,
    Roadmap,
    User,
)

READINESS_WEIGHTS = {
    "resume_score": 0.25,
    "skill_score": 0.30,
    "roadmap_score": 0.15,
    "interview_score": 0.30,
}
_COMPONENT_LABELS = {
    "resume_score": "resume",
    "skill_score": "skill_gap",
    "roadmap_score": "roadmap",
    "interview_score": "interview",
}


def _score(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return max(0.0, min(100.0, result))


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _role_key(value: Any) -> str:
    return value.strip().casefold() if isinstance(value, str) else ""


def _latest_by_user(rows: list[Any]) -> dict[int, Any]:
    latest: dict[int, Any] = {}
    for row in rows:
        latest.setdefault(row.user_id, row)
    return latest


def _empty_evidence() -> dict[str, Any]:
    return {
        "roles": {},
        "gaps": {},
        "resumes": {},
        "roadmaps": {},
        "interviews": {},
        "history": [],
    }


def _roadmap_counts(roadmap: Roadmap | None) -> tuple[int, int]:
    if roadmap is None or not isinstance(roadmap.weeks, list):
        return 0, 0
    total = 0
    completed = 0
    for week in roadmap.weeks:
        if not isinstance(week, dict):
            continue
        tasks = week.get("tasks")
        if not isinstance(tasks, list):
            continue
        for task in tasks:
            if not isinstance(task, dict):
                continue
            total += 1
            completed += task.get("completed") is True
    return completed, total


def _is_completed_interview(session: InterviewSession) -> bool:
    if _score(session.overall_score) is None:
        return False
    questions = session.questions
    scores = session.scores
    if not isinstance(questions, list) or not questions:
        return False
    if not isinstance(scores, list):
        return False
    submitted_scores = {
        item.get("question_index"): _score(item.get("score_out_of_10"))
        for item in scores
        if isinstance(item, dict)
        and isinstance(item.get("question_index"), int)
        and not isinstance(item.get("question_index"), bool)
    }
    return all(
        index in submitted_scores and submitted_scores[index] is not None
        for index in range(len(questions))
    )


def _missing_skills(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    skills: dict[str, str] = {}
    for entry in raw:
        value = entry.get("skill") if isinstance(entry, dict) else entry
        if not isinstance(value, str):
            continue
        skill = value.strip()
        if skill:
            skills.setdefault(skill.casefold(), skill)
    return list(skills.values())


def _weak_skills(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    skills: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, str):
            continue
        skill = item.strip()
        if skill:
            skills.setdefault(skill.casefold(), skill)
    return list(skills.values())


def _date_key(value: datetime | None) -> str | None:
    if not isinstance(value, datetime):
        return None
    return value.strftime("%Y-%m")


def _load_cohort(
    db: Session,
    branch: str | None,
    semester: int | None,
    target_role: str | None,
) -> dict[str, Any]:
    query = db.query(User).filter(User.role == "student")
    if branch:
        query = query.filter(func.lower(User.branch) == branch.strip().casefold())
    if semester is not None:
        query = query.filter(User.semester == semester)
    users = query.order_by(User.id.asc()).all()
    user_ids = [user.id for user in users]
    if not user_ids:
        return {"users": [], "evidence": _empty_evidence()}

    gaps = (
        db.query(GapReport)
        .filter(GapReport.user_id.in_(user_ids))
        .order_by(GapReport.id.desc())
        .all()
    )
    gaps_by_user: dict[int, list[GapReport]] = defaultdict(list)
    for report in gaps:
        gaps_by_user[report.user_id].append(report)
    roles: dict[int, str] = {}
    selected_gaps: dict[int, GapReport] = {}
    selected_role_key = _role_key(target_role)
    filtered_users = []
    for user in users:
        user_reports = gaps_by_user.get(user.id, [])
        effective_role = (
            user.target_role.strip()
            if isinstance(user.target_role, str) and user.target_role.strip()
            else user_reports[0].target_role
            if user_reports and isinstance(user_reports[0].target_role, str)
            else None
        )
        if selected_role_key and _role_key(effective_role) != selected_role_key:
            continue
        matching_reports = [
            report
            for report in user_reports
            if not selected_role_key
            or _role_key(report.target_role) == selected_role_key
        ]
        if not matching_reports and user_reports and not selected_role_key:
            matching_reports = user_reports[:1]
        if matching_reports:
            selected_gaps[user.id] = matching_reports[0]
        roles[user.id] = effective_role or ""
        filtered_users.append(user)

    filtered_ids = [user.id for user in filtered_users]
    if not filtered_ids:
        return {"users": [], "evidence": _empty_evidence()}

    resumes = (
        db.query(Resume)
        .filter(Resume.user_id.in_(filtered_ids))
        .order_by(Resume.id.desc())
        .all()
    )
    roadmaps = (
        db.query(Roadmap)
        .filter(Roadmap.user_id.in_(filtered_ids))
        .order_by(Roadmap.id.desc())
        .all()
    )
    interviews = (
        db.query(InterviewSession)
        .filter(InterviewSession.user_id.in_(filtered_ids))
        .order_by(InterviewSession.id.desc())
        .all()
    )
    history = (
        db.query(ReadinessScoreHistory)
        .filter(ReadinessScoreHistory.user_id.in_(filtered_ids))
        .order_by(ReadinessScoreHistory.created_at.asc(), ReadinessScoreHistory.id.asc())
        .all()
    )
    completed_interviews: dict[int, InterviewSession] = {}
    for session in interviews:
        if _is_completed_interview(session):
            completed_interviews.setdefault(session.user_id, session)

    evidence = {
        "roles": roles,
        "gaps": selected_gaps,
        "resumes": _latest_by_user(resumes),
        "roadmaps": _latest_by_user(roadmaps),
        "interviews": completed_interviews,
        "history": history,
    }
    return {"users": filtered_users, "evidence": evidence}


def _student_metrics(user: User, evidence: dict[str, Any]) -> dict[str, Any]:
    resume = evidence["resumes"].get(user.id)
    gap = evidence["gaps"].get(user.id)
    roadmap = evidence["roadmaps"].get(user.id)
    interview = evidence["interviews"].get(user.id)

    components = {
        "resume_score": _score(resume.ats_score) if resume else None,
        "skill_score": _score(gap.skill_match_pct) if gap else None,
        "roadmap_score": None,
        "interview_score": _score(interview.overall_score) if interview else None,
    }
    completed_tasks, total_tasks = _roadmap_counts(roadmap)
    if total_tasks:
        components["roadmap_score"] = round(completed_tasks / total_tasks * 100, 2)
    available_components = {
        key: value for key, value in components.items() if value is not None
    }
    readiness = (
        round(
            sum(components[key] * weight for key, weight in READINESS_WEIGHTS.items() if components[key] is not None),
            2,
        )
        if available_components
        else None
    )
    return {
        "components": components,
        "readiness_score": readiness,
        "roadmap": {
            "completed_tasks": completed_tasks,
            "total_tasks": total_tasks,
            "progress_pct": (
                round(completed_tasks / total_tasks * 100, 2) if total_tasks else None
            ),
        },
        "gap": gap,
        "interview": interview,
        "evidence_count": len(available_components),
    }


def _trend(history: list[ReadinessScoreHistory], user_ids: set[int]) -> dict[str, Any]:
    latest_per_user_month: dict[tuple[int, str], tuple[datetime, int, float]] = {}
    for row in history:
        month = _date_key(row.created_at)
        score = _score(row.total)
        if row.user_id not in user_ids or month is None or score is None:
            continue
        key = (row.user_id, month)
        current = latest_per_user_month.get(key)
        timestamp = row.created_at
        if current is None or (timestamp, row.id) > (current[0], current[1]):
            latest_per_user_month[key] = (timestamp, row.id, score)
    monthly: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for (user_id, month), (_, _, score) in latest_per_user_month.items():
        monthly[month].append((user_id, score))
    points = [
        {
            "month": month,
            "average_readiness": _mean([score for _, score in entries]),
            "student_count": len(entries),
        }
        for month, entries in sorted(monthly.items())
    ]
    status = "unavailable" if not points else "insufficient_history" if len(points) < 2 else "available"
    return {
        "status": status,
        "basis": "Latest recorded readiness score per student per calendar month; no snapshots are generated.",
        "points": points,
    }


def _summary(cohort: dict[str, Any]) -> dict[str, Any]:
    users = cohort["users"]
    evidence = cohort["evidence"]
    denominator = len(users)
    records = [(user, _student_metrics(user, evidence)) for user in users]
    component_averages: dict[str, dict[str, Any]] = {}
    for component, label in _COMPONENT_LABELS.items():
        values = [
            metrics["components"][component]
            for _, metrics in records
            if metrics["components"][component] is not None
        ]
        component_averages[label] = {
            "average": _mean(values),
            "student_count": len(values),
            "eligible_students": denominator,
        }
    readiness = [
        metrics["readiness_score"]
        for _, metrics in records
        if metrics["readiness_score"] is not None
    ]
    readiness_count = len(readiness)
    missing_counts: dict[str, dict[str, Any]] = {}
    roadmap_progress = [
        metrics["roadmap"]["progress_pct"]
        for _, metrics in records
        if metrics["roadmap"]["progress_pct"] is not None
    ]
    interview_scores = [
        metrics["components"]["interview_score"]
        for _, metrics in records
        if metrics["components"]["interview_score"] is not None
    ]
    for _, metrics in records:
        for skill in _missing_skills(
            metrics["gap"].missing if metrics["gap"] is not None else None
        ):
            key = skill.casefold()
            if key not in missing_counts:
                missing_counts[key] = {"skill": skill, "student_count": 0}
            missing_counts[key]["student_count"] += 1
    top_missing = sorted(
        missing_counts.values(),
        key=lambda item: (-item["student_count"], item["skill"].casefold()),
    )[:10]

    trend = _trend(evidence["history"], {user.id for user in users})
    return {
        "filters": cohort["filters"],
        "cohort": {
            "student_count": denominator,
            "status": "empty" if not denominator else "available",
        },
        "aggregation": {
            "student_role": (
                "Profile target role, falling back to the latest saved gap-report role."
            ),
            "latest_records": (
                "Latest resume, roadmap, and role-matched gap report per student; "
                "latest completed interview per student."
            ),
            "student_counting": (
                "Each student contributes at most once per component and once per "
                "missing skill; absent or malformed evidence is excluded from that "
                "component's sample count."
            ),
            "roadmap": (
                "Cohort progress is the mean of each student's latest roadmap "
                "completion percentage; task totals are also reported."
            ),
        },
        "readiness": {
            "average": _mean(readiness),
            "student_count": readiness_count,
            "eligible_students": denominator,
            "method": (
                "Existing readiness component weights applied to available evidence; "
                "unavailable components contribute no points. Component coverage is reported separately."
            ),
        },
        "components": component_averages,
        "roadmap": {
            "average_progress_pct": _mean(roadmap_progress),
            "student_count": len(roadmap_progress),
            "eligible_students": denominator,
            "completed_tasks": sum(
                metrics["roadmap"]["completed_tasks"] for _, metrics in records
            ),
            "total_tasks": sum(
                metrics["roadmap"]["total_tasks"] for _, metrics in records
            ),
        },
        "interviews": {
            "average_score": _mean(interview_scores),
            "student_count": len(interview_scores),
            "eligible_students": denominator,
            "method": "Latest completed interview per student.",
        },
        "common_missing_skills": {
            "student_count": len(
                [metrics for _, metrics in records if metrics["gap"] is not None]
            ),
            "skills": top_missing,
        },
        "readiness_trend": trend,
    }


def get_cohort_summary(
    db: Session,
    branch: str | None = None,
    semester: int | None = None,
    target_role: str | None = None,
) -> dict[str, Any]:
    cohort = _load_cohort(db, branch, semester, target_role)
    cohort["filters"] = {
        "branch": branch.strip() if branch else None,
        "semester": semester,
        "target_role": target_role.strip() if target_role else None,
    }
    return _summary(cohort)


def get_student_page(
    db: Session,
    branch: str | None,
    semester: int | None,
    target_role: str | None,
    page: int,
    page_size: int,
    sort_by: str,
    sort_order: str,
) -> dict[str, Any]:
    cohort = _load_cohort(db, branch, semester, target_role)
    records = [(user, _student_metrics(user, cohort["evidence"])) for user in cohort["users"]]
    sort_key = {
        "name": lambda pair: (pair[0].name or "").casefold(),
        "branch": lambda pair: (pair[0].branch or "").casefold(),
        "semester": lambda pair: (
            pair[0].semester is None,
            pair[0].semester if pair[0].semester is not None else 0,
        ),
        "readiness": lambda pair: (
            pair[1]["readiness_score"] is None,
            pair[1]["readiness_score"] if pair[1]["readiness_score"] is not None else 0,
        ),
    }[sort_by]
    records.sort(key=lambda pair: (sort_key(pair), pair[0].id), reverse=sort_order == "desc")
    total = len(records)
    selected = records[(page - 1) * page_size : page * page_size]
    return {
        "page": page,
        "page_size": page_size,
        "total_students": total,
        "students": [
            _student_list_item(user, metrics, cohort["evidence"]["roles"].get(user.id))
            for user, metrics in selected
        ],
    }


def _student_list_item(
    user: User,
    metrics: dict[str, Any],
    target_role: str | None,
) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "name": user.name,
        "branch": user.branch,
        "semester": user.semester,
        "target_role": target_role or None,
        "readiness_score": metrics["readiness_score"],
        "evidence_coverage": {
            "available_components": metrics["evidence_count"],
            "total_components": len(READINESS_WEIGHTS),
        },
        "roadmap_progress_pct": metrics["roadmap"]["progress_pct"],
        "interview_score": metrics["components"]["interview_score"],
    }


def get_student_detail(db: Session, student_id: int) -> dict[str, Any] | None:
    user = (
        db.query(User)
        .filter(User.id == student_id, User.role == "student")
        .first()
    )
    if user is None:
        return None
    cohort = _load_cohort(db, user.branch, user.semester, user.target_role)
    metrics = _student_metrics(user, cohort["evidence"])
    gap = metrics["gap"]
    interview = metrics["interview"]
    history = [
        row
        for row in cohort["evidence"]["history"]
        if row.user_id == user.id
    ]
    trend = _trend(history, {user.id})
    return {
        "student": {
            "user_id": user.id,
            "name": user.name,
            "branch": user.branch,
            "semester": user.semester,
            "target_role": cohort["evidence"]["roles"].get(user.id) or None,
        },
        "readiness": {
            "score": metrics["readiness_score"],
            "components": metrics["components"],
            "evidence_coverage": {
                "available_components": metrics["evidence_count"],
                "total_components": len(READINESS_WEIGHTS),
            },
        },
        "skill_gap": {
            "match_pct": metrics["components"]["skill_score"],
            "missing_skills": _missing_skills(gap.missing if gap else None),
        },
        "roadmap": metrics["roadmap"],
        "interview": {
            "score": metrics["components"]["interview_score"],
            "weak_skills": _weak_skills(interview.weak_skills if interview else None),
        },
        "recorded_readiness_history": trend,
    }
