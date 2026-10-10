from __future__ import annotations

from collections import defaultdict
from typing import Optional
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models import AssessmentAttempt, GapReport, LearningCourse, Roadmap, User
from app.services.learning_content import get_canonical_skill, get_vtu_subjects, map_roadmap_task_skill
from app.services.skill_mastery import get_student_mastery


ACTION_ORDER = {"revise": 0, "practise": 1, "reassess": 2, "study": 3}


def _latest_roadmap(db: Session, user_id: int) -> Optional[Roadmap]:
    return (
        db.query(Roadmap)
        .filter(Roadmap.user_id == user_id)
        .order_by(Roadmap.id.desc())
        .first()
    )


def _latest_gap_report(db: Session, user: User) -> Optional[GapReport]:
    query = db.query(GapReport).filter(GapReport.user_id == user.id)
    if user.target_role:
        query = query.filter(GapReport.target_role == user.target_role)
    return query.order_by(GapReport.id.desc()).first()


def _ordered_roadmap_candidates(roadmap: Optional[Roadmap]) -> list[dict]:
    candidates = []
    if not roadmap or not isinstance(roadmap.weeks, list):
        return candidates
    for week_index, week in enumerate(roadmap.weeks):
        if not isinstance(week, dict):
            continue
        tasks = week.get("tasks", [])
        if not isinstance(tasks, list):
            continue
        for task_index, task in enumerate(tasks):
            if not isinstance(task, dict) or task.get("completed") is True:
                continue
            skill_id = map_roadmap_task_skill(task.get("task"))
            if skill_id:
                candidates.append(
                    {
                        "skill_id": skill_id,
                        "task": task.get("task"),
                        "week": week.get("week", week_index + 1),
                        "priority": (week_index, task_index),
                    }
                )
    return candidates


def _gap_candidates(gap: Optional[GapReport]) -> list[dict]:
    if not gap:
        return []
    candidates = []
    for entry in gap.missing or []:
        name = entry.get("skill") if isinstance(entry, dict) else None
        skill_id = get_canonical_skill(name) if isinstance(name, str) else None
        if skill_id:
            candidates.append(
                {
                    "skill_id": skill_id,
                    "task": None,
                    "week": None,
                    "priority": (len(candidates), 0),
                    "status": entry.get("status"),
                }
            )
    return candidates


def _course_lessons(courses: list[LearningCourse]) -> dict[str, dict[str, dict]]:
    by_skill: dict[str, dict[str, dict]] = {}
    for course in courses:
        lessons = course.content.get("lessons", []) if isinstance(course.content, dict) else []
        by_skill[course.skill_id] = {
            lesson["lesson_id"]: lesson
            for lesson in lessons
            if isinstance(lesson, dict) and isinstance(lesson.get("lesson_id"), str)
        }
    return by_skill


def _lesson_for_concept(
    mastery: dict,
    concept: str,
    lessons: dict[str, dict],
) -> tuple[Optional[str], Optional[str]]:
    for assessment in reversed(mastery.get("assessments", [])):
        if any(
            question.get("concept") == concept and question.get("is_correct") is False
            for question in assessment.get("question_review", [])
        ):
            lesson_id = assessment.get("lesson_id")
            if lesson_id in lessons:
                return lesson_id, lessons[lesson_id].get("title")
    for lesson_id, lesson in lessons.items():
        if concept.casefold() in str(lesson.get("title", "")).casefold():
            return lesson_id, lesson.get("title")
    if lessons:
        lesson_id, lesson = next(iter(lessons.items()))
        return lesson_id, lesson.get("title")
    return None, None


def _recommendation(
    *,
    skill_id: str,
    action: str,
    evidence_category: str,
    reason: str,
    evidence: list[str],
    lesson_id: Optional[str],
    lesson_title: Optional[str],
    concept: Optional[str],
    context: dict,
    source_priority: tuple[int, int],
) -> dict:
    if lesson_id:
        href = f"/learn?skill={quote(skill_id)}&lesson={quote(lesson_id)}"
    else:
        href = f"/learn?skill={quote(skill_id)}"
    return {
        "skill_id": skill_id,
        "concept": concept,
        "action": action,
        "evidence_category": evidence_category,
        "reason": reason,
        "evidence": evidence,
        "next_step": _next_step(action, concept, lesson_title),
        "lesson_id": lesson_id,
        "lesson_title": lesson_title,
        "href": href,
        "context": context,
        "_sort": (ACTION_ORDER[action], *source_priority, skill_id.casefold(), concept or ""),
    }


def _next_step(action: str, concept: Optional[str], lesson_title: Optional[str]) -> str:
    target = f"“{concept}”" if concept else f"the lesson “{lesson_title}”" if lesson_title else "this skill"
    if action == "revise":
        return f"Review {target}, then try its lesson practice before reassessing."
    if action == "practise":
        return f"Revisit {target} and complete a focused practice set."
    if action == "reassess":
        return f"Complete another assessment for {target} to gather more evidence."
    return f"Start with {target}, then use an assessment to establish learning evidence."


def _source_context(
    user: User,
    skill_id: str,
    roadmap_item: Optional[dict],
    gap_report: Optional[GapReport],
) -> dict:
    context = {}
    if user.target_role:
        context["target_role"] = user.target_role
    if user.branch:
        context["branch"] = user.branch
    if user.semester is not None:
        context["semester"] = user.semester
    subjects = get_vtu_subjects(user.branch, user.semester, skill_id)
    if subjects:
        context["vtu_subjects"] = subjects
    if roadmap_item and roadmap_item.get("task"):
        context["roadmap_task"] = roadmap_item["task"]
        context["roadmap_week"] = roadmap_item["week"]
    if gap_report:
        context["gap_report_role"] = gap_report.target_role
    return context


def build_recommendations(
    user: User,
    mastery_by_skill: list[dict],
    roadmap_candidates: list[dict],
    gap_candidates: list[dict],
    lessons_by_skill: dict[str, dict[str, dict]],
    requested_skill: Optional[str] = None,
    gap_report: Optional[GapReport] = None,
) -> list[dict]:
    mastery = {item["skill_id"]: item for item in mastery_by_skill}
    roadmap_by_skill: dict[str, list[dict]] = defaultdict(list)
    for candidate in roadmap_candidates:
        roadmap_by_skill[candidate["skill_id"]].append(candidate)
    gap_by_skill: dict[str, list[dict]] = defaultdict(list)
    for candidate in gap_candidates:
        gap_by_skill[candidate["skill_id"]].append(candidate)

    eligible_skills = set(roadmap_by_skill) | set(gap_by_skill) | set(mastery)
    if requested_skill:
        eligible_skills &= {requested_skill}

    candidates = []
    for skill_id in eligible_skills:
        skill_mastery = mastery.get(skill_id)
        roadmap_item = roadmap_by_skill.get(skill_id, [None])[0]
        gap_item = gap_by_skill.get(skill_id, [None])[0]
        lesson_map = lessons_by_skill.get(skill_id, {})
        if roadmap_item:
            source_priority = roadmap_item.get("priority", (10_000, 10_000))
        elif gap_item:
            source_priority = gap_item.get("priority", (20_000, 0))
        else:
            source_priority = (30_000, 0)
        context = _source_context(user, skill_id, roadmap_item, gap_report)

        if skill_mastery:
            repeated_review = [
                item
                for item in skill_mastery.get("concepts", [])
                if item.get("status") == "review"
            ]
            for index, item in enumerate(repeated_review):
                lesson_id, lesson_title = _lesson_for_concept(
                    skill_mastery, item["concept"], lesson_map
                )
                candidates.append(
                    _recommendation(
                        skill_id=skill_id,
                        action="revise",
                        evidence_category="demonstrated_weakness",
                        reason=(
                            f"Assessment evidence identifies {item['concept']} as a review area "
                            f"({item['correct']}/{item['total']} correct across "
                            f"{item['evidence_assessments']} assessments)."
                        ),
                        evidence=[
                            f"{item['correct']} of {item['total']} answers correct for this concept.",
                            f"Evidence spans {item['evidence_assessments']} distinct assessments.",
                        ],
                        lesson_id=lesson_id,
                        lesson_title=lesson_title,
                        concept=item["concept"],
                        context=context,
                        source_priority=(index, *source_priority),
                    )
                )
            if repeated_review:
                continue

            if skill_mastery["status"] == "insufficient_evidence":
                assessment_count = skill_mastery["evidence_assessments"]
                question_count = skill_mastery["evidence_questions"]
                latest_id = skill_mastery.get("latest_assessment_id")
                latest = next(
                    (
                        item
                        for item in skill_mastery.get("assessments", [])
                        if item.get("assessment_id") == latest_id
                    ),
                    None,
                )
                wrong_question = next(
                    (
                        question
                        for question in (latest or {}).get("question_review", [])
                        if question.get("is_correct") is False
                    ),
                    None,
                )
                concept = wrong_question.get("concept") if wrong_question else None
                lesson_id, lesson_title = _lesson_for_concept(
                    skill_mastery, concept, lesson_map
                ) if concept else (None, None)
                if lesson_id is None and lesson_map:
                    lesson_id, lesson = next(iter(lesson_map.items()))
                    lesson_title = lesson.get("title")
                reason = (
                    "There is not yet enough submitted assessment evidence to determine progress; "
                    "this is not evidence of failure."
                )
                evidence = [
                    f"{assessment_count} submitted assessment(s); "
                    f"{question_count} answered question(s).",
                    "The skill mastery service currently reports insufficient evidence.",
                ]
                if concept:
                    reason = (
                        f"Evidence is still insufficient for a skill-level conclusion, and the latest "
                        f"assessment included a missed question about {concept}; this is not evidence of failure."
                    )
                    evidence.append(f"The latest attempt included an incorrect response about {concept}.")
                candidates.append(
                    _recommendation(
                        skill_id=skill_id,
                        action="reassess" if assessment_count else "study",
                        evidence_category="insufficient_evidence",
                        reason=reason,
                        evidence=evidence,
                        lesson_id=lesson_id,
                        lesson_title=lesson_title,
                        concept=concept,
                        context=context,
                        source_priority=(0, *source_priority),
                    )
                )
                continue

            latest_attempt = skill_mastery.get("assessments", [])
            latest_attempt = latest_attempt[-1] if latest_attempt else None
            missed = next(
                (
                    question
                    for question in (latest_attempt or {}).get("question_review", [])
                    if question.get("is_correct") is False
                ),
                None,
            )
            if missed:
                concept = missed.get("concept")
                lesson_id, lesson_title = _lesson_for_concept(skill_mastery, concept, lesson_map)
                candidates.append(
                    _recommendation(
                        skill_id=skill_id,
                        action="practise",
                        evidence_category="demonstrated_weakness",
                        reason=(
                            f"The latest assessment included an incorrect response about {concept}; "
                            "a focused practice session can help revisit it."
                        ),
                        evidence=[
                            f"Latest assessment score: {skill_mastery.get('latest_assessment_score_pct')}%.",
                            f"An incorrect answer was recorded for {concept}.",
                        ],
                        lesson_id=lesson_id,
                        lesson_title=lesson_title,
                        concept=concept,
                        context=context,
                        source_priority=(0, *source_priority),
                    )
                )
                continue
            candidates.append(
                _recommendation(
                    skill_id=skill_id,
                    action="reassess",
                    evidence_category="upcoming_learning",
                    reason=(
                        "The latest assessment did not identify a missed question or repeated concept "
                        "review area; continue learning and reassess to build evidence."
                    ),
                    evidence=[
                        f"Cumulative assessment evidence score: {skill_mastery.get('score_pct')}%.",
                        f"Latest assessment score: {skill_mastery.get('latest_assessment_score_pct')}%.",
                    ],
                    lesson_id=next(iter(lesson_map), None),
                    lesson_title=next(iter(lesson_map.values()), {}).get("title"),
                    concept=None,
                    context=context,
                    source_priority=(1, *source_priority),
                )
            )
            continue

        if roadmap_item:
            task_text = roadmap_item.get("task")
            study_type = "revise" if task_text and "[REVISE" in task_text.upper() else "study"
            if gap_item and gap_item.get("status") == "learn from scratch":
                study_type = "study"
            lesson_id, lesson_title = next(iter(lesson_map.items()), (None, {}))
            roadmap_timing = (
                f" for week {roadmap_item['week']}"
                if roadmap_item.get("week")
                else ""
            )
            candidates.append(
                _recommendation(
                    skill_id=skill_id,
                    action=study_type,
                    evidence_category="upcoming_learning",
                    reason=(
                        f"The current roadmap lists this as an upcoming skill task{roadmap_timing}; "
                        "there is no demonstrated weakness for this skill."
                    ),
                    evidence=[
                        f"Roadmap task: {task_text}" if task_text else "Included in the current role skill-gap report.",
                        (
                            "No submitted assessment evidence is available; this is not evidence of failure."
                            if not skill_mastery
                            else "The available assessment evidence has not demonstrated a weakness."
                        ),
                    ],
                    lesson_id=lesson_id,
                    lesson_title=lesson_title.get("title"),
                    concept=None,
                    context=context,
                    source_priority=(2, *source_priority),
                )
            )
        elif gap_item:
            lesson_id, lesson = next(iter(lesson_map.items()), (None, {}))
            candidates.append(
                _recommendation(
                    skill_id=skill_id,
                    action="study",
                    evidence_category="upcoming_learning",
                    reason=(
                        "The latest role skill-gap report lists this canonical skill as missing; "
                        "this is an upcoming learning priority, not an assessment-demonstrated weakness."
                    ),
                    evidence=[
                        f"Role skill-gap status: {gap_item.get('status') or 'missing'}.",
                        "No roadmap task is available for this skill.",
                        "No submitted assessment evidence is available.",
                    ],
                    lesson_id=lesson_id,
                    lesson_title=lesson.get("title"),
                    concept=None,
                    context=context,
                    source_priority=(2, *source_priority),
                )
            )

    candidates.sort(key=lambda item: item["_sort"])
    results = []
    for candidate in candidates:
        candidate.pop("_sort", None)
        results.append(candidate)
    return results


def get_recommendations(
    db: Session,
    user: User,
    requested_skill: Optional[str] = None,
    max_results: Optional[int] = 5,
) -> dict:
    roadmap = _latest_roadmap(db, user.id)
    gap = _latest_gap_report(db, user)
    mastery = get_student_mastery(db, user.id)
    courses = (
        db.query(LearningCourse)
        .filter(LearningCourse.user_id == user.id)
        .all()
    )
    roadmap_candidates = _ordered_roadmap_candidates(roadmap)
    gap_candidates = _gap_candidates(gap)
    if requested_skill:
        roadmap_candidates = [item for item in roadmap_candidates if item["skill_id"] == requested_skill]
        gap_candidates = [item for item in gap_candidates if item["skill_id"] == requested_skill]
    recommendations = build_recommendations(
        user=user,
        mastery_by_skill=mastery,
        roadmap_candidates=roadmap_candidates,
        gap_candidates=gap_candidates,
        lessons_by_skill=_course_lessons(courses),
        requested_skill=requested_skill,
        gap_report=gap,
    )
    return {
        "recommendations": recommendations[:max_results] if max_results is not None else recommendations,
        "profile_context": {
            key: value
            for key, value in {
                "target_role": user.target_role,
                "branch": user.branch,
                "semester": user.semester,
            }.items()
            if value is not None
        },
        "notice": (
            "Recommendations use assessment evidence for learning actions; roadmap and role-gap data provide "
            "planning context only. They do not change mastery records or placement readiness."
        ),
    }
