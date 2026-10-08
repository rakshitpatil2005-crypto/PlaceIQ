from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models import User, Resume, GapReport
from app.services.gap_analyzer import analyze_skill_gap

router = APIRouter()

class GapRequest(BaseModel):
    target_role: str

@router.post("/gap/analyze")
def analyze_gap(request: GapRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user.branch or not current_user.semester:
        raise HTTPException(status_code=400, detail="Please update your profile.")
        
    latest_resume = db.query(Resume).filter(Resume.user_id == current_user.id).order_by(Resume.id.desc()).first()
    resume_skills = latest_resume.extracted_skills if latest_resume else []
    
    try:
        gap_data = analyze_skill_gap(
            branch=current_user.branch,
            current_sem=current_user.semester,
            target_role=request.target_role,
            resume_skills=resume_skills
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    # Save a record in SQLite
    report = GapReport(
        user_id=current_user.id,
        target_role=request.target_role,
        covered_by_syllabus=gap_data["covered_by_syllabus"],
        from_resume=gap_data["from_resume"],
        missing=gap_data["missing"],
        skill_match_pct=gap_data["skill_match_pct"]
    )
    db.add(report)
    current_user.target_role = request.target_role
    db.commit()
    
    # Return the clean dictionary directly so frontend receives all keys
    return gap_data