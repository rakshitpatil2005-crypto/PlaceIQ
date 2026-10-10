from __future__ import annotations

from copy import deepcopy

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import Roadmap, User
from app.services.adaptive_recommendations import get_recommendations
from app.services.learning_content import map_roadmap_task_skill


def _annotate_future_tasks(
    weeks: list,
    recommendations: list[dict],
) -> tuple[list, int]:
    if not isinstance(weeks, list):
        return deepcopy(weeks), 0

    recommendation_by_skill = {}
    for item in recommendations:
        if isinstance(item.get("skill_id"), str):
            recommendation_by_skill.setdefault(item["skill_id"], item)
    updated_weeks = deepcopy(weeks)
    candidates = []

    for week_index, week in enumerate(updated_weeks):
        if not isinstance(week, dict) or not isinstance(week.get("tasks"), list):
            continue
        for task_index, task in enumerate(week["tasks"]):
            if not isinstance(task, dict) or task.get("completed") is True:
                continue
            skill_id = map_roadmap_task_skill(task.get("task"))
            recommendation = recommendation_by_skill.get(skill_id)
            if recommendation:
                candidates.append((week_index, task_index, recommendation))

    candidates.sort(
        key=lambda item: (
            item[2].get("_priority", 10_000),
            item[0],
            item[1],
            item[2]["skill_id"].casefold(),
        )
    )
    priority_by_location = {
        (week_index, task_index): (priority, recommendation)
        for priority, (week_index, task_index, recommendation) in enumerate(candidates, start=1)
    }

    for week_index, week in enumerate(updated_weeks):
        if not isinstance(week, dict) or not isinstance(week.get("tasks"), list):
            continue
        for task_index, task in enumerate(week["tasks"]):
            if not isinstance(task, dict) or task.get("completed") is True:
                continue
            ranked = priority_by_location.get((week_index, task_index))
            if ranked is None:
                continue
            priority, recommendation = ranked
            task["adaptive"] = {
                "priority": priority,
                "action": recommendation["action"],
                "evidence_category": recommendation["evidence_category"],
                "reason": recommendation["reason"],
                "evidence": recommendation["evidence"],
                "context": recommendation["context"],
            }

    return updated_weeks, len(candidates)


def adapt_student_roadmap(db: Session, user: User, roadmap: Roadmap) -> dict:
    recommendation_data = get_recommendations(db, user, max_results=None)
    recommendations = recommendation_data["recommendations"]

    # Preserve each task's current index: the existing completion API addresses tasks by index.
    for index, item in enumerate(recommendations):
        item["_priority"] = index

    weeks, adapted_tasks = _annotate_future_tasks(roadmap.weeks, recommendations)
    if weeks != roadmap.weeks:
        roadmap.weeks = weeks
        flag_modified(roadmap, "weeks")
        db.commit()
        db.refresh(roadmap)

    return {
        "message": (
            "Future task priorities were adapted using submitted assessment evidence."
            if adapted_tasks
            else "No incomplete roadmap tasks could be matched to current learning evidence."
        ),
        "adapted_tasks": adapted_tasks,
        "roadmap": roadmap,
    }
