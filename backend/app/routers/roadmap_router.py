from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import Optional, List, Any
from app.database import get_db
from app.auth import get_current_user
from app.models import User, Roadmap, Resume, GapReport
from app.services.gap_analyzer import analyze_skill_gap
from app.services.roadmap_generator import generate_personalized_roadmap

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class RoadmapRequest(BaseModel):
    target_role: str


class TaskToggleRequest(BaseModel):
    week_index: int
    task_index: int
    completed: Optional[bool] = None


class RoadmapUpdateRequest(BaseModel):
    weeks: List[Any]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/roadmap")
def get_roadmap(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Fetch the latest generated roadmap for the current user."""
    roadmap = db.query(Roadmap).filter(Roadmap.user_id == current_user.id).order_by(Roadmap.id.desc()).first()
    return roadmap


@router.post("/roadmap/generate")
def generate_roadmap(request: RoadmapRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Generate a personalized 6-week learning roadmap based on the user's VTU-aware skill gap analysis.
    """
    if not current_user.branch or not current_user.semester:
        raise HTTPException(status_code=400, detail="Please update your profile first.")

    # 1. Fetch latest resume skills
    latest_resume = db.query(Resume).filter(Resume.user_id == current_user.id).order_by(Resume.id.desc()).first()
    resume_skills = latest_resume.extracted_skills if latest_resume else []

    # 2. Get latest gap report or compute VTU skill gap for target role
    latest_gap = (
        db.query(GapReport)
        .filter(GapReport.user_id == current_user.id, GapReport.target_role == request.target_role)
        .order_by(GapReport.id.desc())
        .first()
    )

    if latest_gap:
        gap_data = {
            "target_role": latest_gap.target_role,
            "covered_by_syllabus": latest_gap.covered_by_syllabus or [],
            "from_resume": latest_gap.from_resume or [],
            "missing": latest_gap.missing or [],
            "skill_match_pct": latest_gap.skill_match_pct or 0,
        }
    else:
        gap_data = analyze_skill_gap(
            branch=current_user.branch,
            current_sem=current_user.semester,
            target_role=request.target_role,
            resume_skills=resume_skills,
        )

    # 3. Generate personalized 6-week roadmap
    roadmap_data = generate_personalized_roadmap(gap_data=gap_data, target_role=request.target_role)

    weeks = roadmap_data.get("weeks", [])

    # 4. Save to database
    new_roadmap = Roadmap(
        user_id=current_user.id,
        weeks=weeks,
    )
    db.add(new_roadmap)
    db.commit()
    db.refresh(new_roadmap)

    return new_roadmap


@router.post("/roadmap/task/toggle")
@router.put("/roadmap/task/toggle")
def toggle_roadmap_task(
    request: TaskToggleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Toggle or explicitly set the completion state of a specific task in the user's latest roadmap.
    Persists the updated task state in SQLite.
    """
    roadmap = db.query(Roadmap).filter(Roadmap.user_id == current_user.id).order_by(Roadmap.id.desc()).first()

    if not roadmap or not roadmap.weeks:
        raise HTTPException(status_code=404, detail="No active roadmap found.")

    weeks = list(roadmap.weeks)

    if request.week_index < 0 or request.week_index >= len(weeks):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid week_index {request.week_index}. Valid range: 0 to {len(weeks) - 1}",
        )

    week = weeks[request.week_index]
    tasks = week.get("tasks", [])

    if request.task_index < 0 or request.task_index >= len(tasks):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task_index {request.task_index}. Valid range: 0 to {len(tasks) - 1}",
        )

    # Update completion state
    if request.completed is not None:
        tasks[request.task_index]["completed"] = request.completed
    else:
        current_state = bool(tasks[request.task_index].get("completed", False))
        tasks[request.task_index]["completed"] = not current_state

    # Save to database and flag JSON column modification
    roadmap.weeks = weeks
    flag_modified(roadmap, "weeks")
    db.commit()
    db.refresh(roadmap)

    return {"message": "Task completion state updated", "roadmap": roadmap}


@router.put("/roadmap/progress")
def update_roadmap_progress(
    request: RoadmapUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update the complete weeks structure for the user's latest roadmap.
    Persists all week and task states in SQLite.
    """
    roadmap = db.query(Roadmap).filter(Roadmap.user_id == current_user.id).order_by(Roadmap.id.desc()).first()

    if not roadmap:
        raise HTTPException(status_code=404, detail="No active roadmap found.")

    roadmap.weeks = request.weeks
    flag_modified(roadmap, "weeks")
    db.commit()
    db.refresh(roadmap)

    return {"message": "Roadmap progress saved successfully", "roadmap": roadmap}