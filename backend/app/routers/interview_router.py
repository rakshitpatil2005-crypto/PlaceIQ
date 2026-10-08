from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from app.database import get_db
from app.auth import get_current_user
from app.models import User, Resume, GapReport, InterviewSession
from app.services.gap_analyzer import analyze_skill_gap
from app.services.interview_generator import generate_mock_interview
from app.services.interview_evaluator import evaluate_candidate_answer

router = APIRouter()


class AnswerSubmission(BaseModel):
    question: str
    answer: str
    target_role: str
    question_index: Optional[int] = None


@router.get("/interview/session")
def get_current_interview_session(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Retrieve the active/latest interview session for the user, including questions, answers, and scores.
    Enables state restoration across page refreshes and navigation.
    """
    session = (
        db.query(InterviewSession)
        .filter(InterviewSession.user_id == current_user.id)
        .order_by(InterviewSession.id.desc())
        .first()
    )
    if not session:
        return {"session": None}

    return {
        "session_id": session.id,
        "target_role": session.target_role,
        "questions": session.questions or [],
        "answers": session.answers or [],
        "scores": session.scores or [],
        "created_at": session.created_at,
    }


@router.get("/interview/generate")
def generate_interview_questions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Generate a personalized 8-question mock interview session (5 Technical + 3 HR)
    tailored to the student's target role, VTU skill gaps, weak skills, and resume projects.
    """
    # 1. Fetch latest user assets
    latest_resume = db.query(Resume).filter(Resume.user_id == current_user.id).order_by(Resume.id.desc()).first()
    latest_gap = db.query(GapReport).filter(GapReport.user_id == current_user.id).order_by(GapReport.id.desc()).first()
    prev_session = db.query(InterviewSession).filter(InterviewSession.user_id == current_user.id).order_by(InterviewSession.id.desc()).first()

    # Determine target role
    target_role = (
        current_user.target_role
        or (latest_gap.target_role if latest_gap else None)
        or "Software Engineer"
    )

    # Resume assets
    resume_skills = latest_resume.extracted_skills if (latest_resume and latest_resume.extracted_skills) else []
    projects = latest_resume.projects if (latest_resume and latest_resume.projects) else []

    # Skill gaps
    if latest_gap:
        missing_list = [item.get("skill") for item in (latest_gap.missing or []) if item.get("skill")]
        revise_list = [item.get("skill") for item in (latest_gap.covered_by_syllabus or []) if item.get("status") == "revise and add to resume"]
        gap_skills = missing_list + revise_list
    else:
        # Compute on the fly if no gap report saved
        gap_data = analyze_skill_gap(
            branch=current_user.branch or "CSE",
            current_sem=current_user.semester or 5,
            target_role=target_role,
            resume_skills=resume_skills,
        )
        missing_list = [item.get("skill") for item in gap_data["missing"] if item.get("skill")]
        revise_list = [item.get("skill") for item in gap_data["covered_by_syllabus"] if item.get("status") == "revise and add to resume"]
        gap_skills = missing_list + revise_list

    # Weak skills from prior session
    weak_skills = (prev_session.weak_skills if (prev_session and prev_session.weak_skills) else [])

    # 2. Generate 8-question mock interview
    result = generate_mock_interview(
        target_role=target_role,
        gap_skills=gap_skills,
        weak_skills=weak_skills,
        projects=projects,
    )

    questions = result.get("questions", [])

    # 3. Persist new interview session in database
    session = InterviewSession(
        user_id=current_user.id,
        target_role=target_role,
        questions=questions,
        answers=[],
        scores=[],
        weak_skills=weak_skills,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return {"target_role": target_role, "questions": questions}


@router.post("/interview/evaluate")
def evaluate_answer(
    submission: AnswerSubmission,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Evaluate a candidate's answer for a specific interview question (0-10 score, strengths,
    improvements, feedback, ideal answer hint) and persist the state in SQLite.
    """
    if not submission.question or not submission.question.strip():
        raise HTTPException(status_code=400, detail="Question string is required.")
    if not submission.answer or not submission.answer.strip():
        raise HTTPException(status_code=400, detail="Answer text cannot be empty.")

    # 1. Perform strict evaluation using evaluator service
    eval_result = evaluate_candidate_answer(
        question=submission.question,
        answer=submission.answer,
        target_role=submission.target_role,
    )

    # 2. Find active session and persist answer + score + feedback in SQLite
    session = (
        db.query(InterviewSession)
        .filter(InterviewSession.user_id == current_user.id)
        .order_by(InterviewSession.id.desc())
        .first()
    )

    if session:
        answers_list = list(session.answers or [])
        scores_list = list(session.scores or [])

        q_idx = submission.question_index
        if q_idx is None and session.questions:
            # Try matching by question string
            for idx, q in enumerate(session.questions):
                if q.strip().lower() == submission.question.strip().lower():
                    q_idx = idx
                    break

        ans_record = {
            "question": submission.question,
            "answer": submission.answer,
            "question_index": q_idx,
        }

        score_record = {
            "question_index": q_idx,
            "question": submission.question,
            "score_out_of_10": eval_result["score_out_of_10"],
            "strengths": eval_result["strengths"],
            "improvements": eval_result["improvements"],
            "feedback": eval_result["feedback"],
            "ideal_answer": eval_result["ideal_answer"],
        }

        answers_list.append(ans_record)
        scores_list.append(score_record)

        session.answers = answers_list
        session.scores = scores_list

        flag_modified(session, "answers")
        flag_modified(session, "scores")
        db.commit()
        db.refresh(session)

    return eval_result
