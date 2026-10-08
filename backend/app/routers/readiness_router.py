from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import ReadinessScore, ReadinessScoreHistory, User
from app.services.readiness_service import persist_readiness_score

router = APIRouter()


@router.get("/readiness")
@router.get("/readiness/score")
def get_readiness_score(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    snapshot = persist_readiness_score(db, current_user)
    current = (
        db.query(ReadinessScore)
        .filter(ReadinessScore.user_id == current_user.id)
        .order_by(ReadinessScore.id.desc())
        .first()
    )
    return {
        "user_id": current_user.id,
        "readiness_score": snapshot["total"],
        "resume_score": snapshot["resume_score"],
        "skill_score": snapshot["skill_score"],
        "roadmap_score": snapshot["roadmap_score"],
        "interview_score": snapshot["interview_score"],
        "current": {
            "id": current.id if current else None,
            "resume_score": current.resume_score if current else snapshot["resume_score"],
            "skill_score": current.skill_score if current else snapshot["skill_score"],
            "roadmap_score": current.roadmap_score if current else snapshot["roadmap_score"],
            "interview_score": current.interview_score if current else snapshot["interview_score"],
            "total": current.total if current else snapshot["total"],
        },
        "history_written": snapshot["history_written"],
    }


@router.get("/readiness/history")
def get_readiness_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(ReadinessScoreHistory)
        .filter(ReadinessScoreHistory.user_id == current_user.id)
        .order_by(ReadinessScoreHistory.created_at.desc())
        .all()
    )
    return {
        "history": [
            {
                "id": row.id,
                "resume_score": row.resume_score,
                "skill_score": row.skill_score,
                "roadmap_score": row.roadmap_score,
                "interview_score": row.interview_score,
                "total": row.total,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }


@router.post("/readiness/refresh")
def refresh_readiness_score(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    snapshot = persist_readiness_score(db, current_user)
    return {
        "user_id": current_user.id,
        "readiness_score": snapshot["total"],
        "resume_score": snapshot["resume_score"],
        "skill_score": snapshot["skill_score"],
        "roadmap_score": snapshot["roadmap_score"],
        "interview_score": snapshot["interview_score"],
        "history_written": snapshot["history_written"],
    }
