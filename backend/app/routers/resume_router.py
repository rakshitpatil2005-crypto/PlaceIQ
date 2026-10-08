from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models import User, Resume
from app.services.resume_parser import extract_text_from_pdf
from app.services.skill_extractor import analyze_resume
from app.services.ats_engine import score_against_jd

router = APIRouter()


# ── Existing endpoint (unchanged API contract) ────────────────────────────────

@router.post("/resume/upload")
async def upload_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    contents = await file.read()

    try:
        raw_text = extract_text_from_pdf(contents)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not raw_text:
        raise HTTPException(status_code=400, detail="Could not extract text from PDF.")

    analysis = analyze_resume(raw_text)
    if "error" in analysis:
        raise HTTPException(status_code=500, detail=f"AI Error: {analysis['error']}")

    new_resume = Resume(
        user_id=current_user.id,
        filename=file.filename,
        raw_text=raw_text,
        extracted_skills=analysis.get("skills", []),
        projects=analysis.get("projects", []),
        ats_score=analysis.get("ats_score", 0),
    )
    db.add(new_resume)
    db.commit()
    db.refresh(new_resume)

    return {"message": "Resume processed successfully", "data": analysis}


# ── New endpoint: score resume against a job description ─────────────────────

class JDScoreRequest(BaseModel):
    jd_text: str


@router.post("/resume/score-jd")
def score_resume_against_jd(
    request: JDScoreRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Deterministically score the user's latest resume against a job description.

    Extracts all recognised technical skills from the JD text and computes
    keyword-overlap with the resume's extracted skills. No LLM call.
    """
    latest_resume = (
        db.query(Resume)
        .filter(Resume.user_id == current_user.id)
        .order_by(Resume.id.desc())
        .first()
    )

    if not latest_resume:
        raise HTTPException(
            status_code=404,
            detail="No resume found. Please upload your resume first.",
        )

    resume_skills = latest_resume.extracted_skills or []
    resume_text = latest_resume.raw_text or ""

    result = score_against_jd(
        resume_text=resume_text,
        resume_skills=resume_skills,
        jd_text=request.jd_text,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result