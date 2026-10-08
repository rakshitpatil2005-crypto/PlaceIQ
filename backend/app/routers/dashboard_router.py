from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models import User, Resume, GapReport, Roadmap

router = APIRouter()

@router.get("/dashboard/stats")
def get_dashboard_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 1. Fetch Latest Resume Stats
    latest_resume = db.query(Resume).filter(Resume.user_id == current_user.id).order_by(Resume.id.desc()).first()
    ats_score = latest_resume.ats_score if latest_resume else 0
    total_skills = len(latest_resume.extracted_skills) if latest_resume and latest_resume.extracted_skills else 0

    # 2. Fetch Latest Gap Report Stats
    latest_gap = db.query(GapReport).filter(GapReport.user_id == current_user.id).order_by(GapReport.id.desc()).first()
    skill_match_pct = latest_gap.skill_match_pct if latest_gap else 0
    target_role = latest_gap.target_role if latest_gap else "None Selected"

    # 3. Calculate Roadmap Progress
    latest_roadmap = db.query(Roadmap).filter(Roadmap.user_id == current_user.id).order_by(Roadmap.id.desc()).first()
    total_tasks = 0
    completed_tasks = 0
    
    if latest_roadmap and latest_roadmap.weeks:
        for week in latest_roadmap.weeks:
            for task in week.get("tasks", []):
                total_tasks += 1
                if task.get("completed"):
                    completed_tasks += 1
                    
    roadmap_progress = round((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0

    return {
        "ats_score": ats_score,
        "total_skills_extracted": total_skills,
        "skill_match_pct": skill_match_pct,
        "target_role": target_role,
        "roadmap_progress": roadmap_progress,
    }