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
from app.services.skill_extractor import normalize_skill

router = APIRouter()


def _normalize_skill_list(raw_skills: list) -> list[str]:
    items: list[str] = []
    seen = set()
    for skill in raw_skills or []:
        if not isinstance(skill, str):
            continue
        canonical = normalize_skill(skill).strip()
        if canonical and canonical.lower() not in seen:
            seen.add(canonical.lower())
            items.append(canonical)
    return items


def _infer_weak_skills(session: InterviewSession, db: Session, current_user: User) -> list[str]:
    scores = list(session.scores or [])
    questions = list(session.questions or [])
    if not scores:
        return list(session.weak_skills or [])

    skill_hints = {
        "database": "SQL",
        "sql": "SQL",
        "rest": "REST APIs",
        "api": "REST APIs",
        "python": "Python",
        "java": "Java",
        "docker": "Docker",
        "kubernetes": "Kubernetes",
        "aws": "AWS",
        "cloud": "Cloud",
        "system design": "System Design",
        "design": "System Design",
        "network": "Computer Networks",
        "operating system": "Operating Systems",
        "algorithms": "Algorithms",
        "data structure": "Data Structures",
        "javascript": "JavaScript",
        "react": "React",
        "node": "Node.js",
        "microservices": "System Design",
        "c++": "C++",
        "c programming": "C",
        "embedded": "Embedded Systems",
        "microcontroller": "Microcontrollers",
        "vhdl": "VHDL",
        "verilog": "Verilog",
    }

    weak: list[str] = []
    seen = set()

    for record in scores:
        if not isinstance(record, dict):
            continue
        if record.get("question_index") is not None and int(record.get("question_index", -1)) >= 5:
            continue

        score = record.get("score_out_of_10")
        try:
            score_val = int(round(float(score)))
        except (TypeError, ValueError):
            continue
        if score_val >= 5:
            continue

        q_idx = record.get("question_index")
        q_text = record.get("question") or (questions[q_idx] if isinstance(q_idx, int) and 0 <= q_idx < len(questions) else "")
        if not q_text:
            continue

        q_lower = str(q_text).lower()
        detected = None
        for keyword, match_skill in skill_hints.items():
            if keyword in q_lower:
                detected = match_skill
                break

        if detected is None:
            detected = "Core Technical Fundamentals"

        canonical = normalize_skill(detected)
        if canonical and canonical.lower() not in seen:
            seen.add(canonical.lower())
            weak.append(canonical)

    if weak:
        return weak[:3]
    if session.weak_skills:
        return [normalize_skill(str(s)) for s in session.weak_skills if str(s).strip()][:3]
    return []


def _compute_interview_completion(session: InterviewSession, db: Session, current_user: User) -> dict:
    questions = list(session.questions or [])
    scores = list(session.scores or [])
    if not questions:
        return {"completed": False, "overall_score": 0.0, "weak_skills": [], "final_feedback": "No interview questions were generated."}
    if not scores:
        return {"completed": False, "overall_score": 0.0, "weak_skills": [], "final_feedback": "Interview is in progress. Complete all questions to receive a final score."}

    completed = len(scores) >= len(questions)
    avg_score = sum(int(item.get("score_out_of_10", 0)) for item in scores if isinstance(item, dict)) / len(scores)
    overall_score = round(float(avg_score * 10), 2)
    weak_skills = _infer_weak_skills(session, db, current_user)

    if completed:
        weak_text = ", ".join(weak_skills) if weak_skills else "core interview fundamentals"
        final_feedback = (
            f"Interview completed for {session.target_role or 'your target role'}. "
            f"Overall score: {overall_score:.2f}/100. "
            f"Focus areas: {weak_text}. Review the scored responses and prioritize technical revision before your next mock interview."
        )
    else:
        final_feedback = (
            f"Interview in progress. Current average score: {overall_score:.2f}/100. "
            f"Complete the remaining questions to finish the full evaluation."
        )

    return {
        "completed": completed,
        "overall_score": overall_score,
        "weak_skills": weak_skills,
        "final_feedback": final_feedback,
    }


def _persist_interview_completion(session: InterviewSession, db: Session, current_user: User) -> dict:
    completion = _compute_interview_completion(session, db, current_user)
    session.weak_skills = completion["weak_skills"]
    session.overall_score = completion["overall_score"]
    flag_modified(session, "weak_skills")
    flag_modified(session, "overall_score")
    db.commit()
    db.refresh(session)
    return completion


def _sync_weak_skills_to_gap_report(current_user: User, db: Session, weak_skills: list[str]) -> None:
    if not weak_skills:
        return

    latest_gap = (
        db.query(GapReport)
        .filter(GapReport.user_id == current_user.id)
        .order_by(GapReport.id.desc())
        .first()
    )

    if not latest_gap:
        resume_skills = []
        gap_data = analyze_skill_gap(
            branch=current_user.branch or "CSE",
            current_sem=current_user.semester or 5,
            target_role=current_user.target_role or "Software Engineer",
            resume_skills=resume_skills,
        )
        latest_gap = GapReport(
            user_id=current_user.id,
            target_role=current_user.target_role or gap_data.get("target_role") or "Software Engineer",
            covered_by_syllabus=gap_data.get("covered_by_syllabus") or [],
            from_resume=gap_data.get("from_resume") or [],
            missing=gap_data.get("missing") or [],
            skill_match_pct=gap_data.get("skill_match_pct") or 0,
        )
        db.add(latest_gap)
        db.commit()
        db.refresh(latest_gap)

    existing_missing = list(latest_gap.missing or [])
    seen = {normalize_skill(str(item.get("skill"))).lower() for item in existing_missing if isinstance(item, dict) and item.get("skill")}

    for skill in weak_skills:
        canonical = normalize_skill(str(skill))
        if not canonical:
            continue
        normalized = canonical.lower()
        if normalized in seen:
            continue
        existing_missing.append({"skill": canonical, "status": "weak from interview"})
        seen.add(normalized)

    latest_gap.missing = existing_missing
    flag_modified(latest_gap, "missing")
    db.commit()
    db.refresh(latest_gap)


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

    completion = _compute_interview_completion(session, db, current_user)
    return {
        "session_id": session.id,
        "target_role": session.target_role,
        "questions": session.questions or [],
        "answers": session.answers or [],
        "scores": session.scores or [],
        "weak_skills": session.weak_skills or completion["weak_skills"],
        "overall_score": completion["overall_score"],
        "completed": completion["completed"],
        "final_feedback": completion["final_feedback"],
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

    # Weak skills from prior session and the latest gap report should both influence the next interview.
    weak_skills = (prev_session.weak_skills if (prev_session and prev_session.weak_skills) else [])
    gap_skills = list(dict.fromkeys(gap_skills + [skill for skill in weak_skills if skill]))

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
        overall_score=0.0,
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
        completion = _persist_interview_completion(session, db, current_user)
        _sync_weak_skills_to_gap_report(current_user, db, completion["weak_skills"])
        db.refresh(session)

        return {
            **eval_result,
            "completed": completion["completed"],
            "overall_score": completion["overall_score"],
            "weak_skills": completion["weak_skills"],
            "final_feedback": completion["final_feedback"],
        }

    return {**eval_result, "completed": False, "overall_score": 0.0, "weak_skills": [], "final_feedback": eval_result["feedback"]}
