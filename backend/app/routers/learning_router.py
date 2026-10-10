from __future__ import annotations

from datetime import datetime
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.auth import get_current_user
from app.database import get_db
from app.models import AssessmentAttempt, GapReport, LearningCourse, PracticeAttempt, PracticeSession, Roadmap, User
from app.services.assessment_engine import (
    AssessmentSubmission,
    generate_assessment,
    score_assessment,
)
from app.services.adaptive_recommendations import get_recommendations
from app.services.learning_content import (
    LessonContent,
    generate_learning_content,
    get_canonical_skill,
    get_vtu_subjects,
    map_roadmap_task_skill,
)
from app.services.practice_engine import PracticeQuestion, generate_practice_set, grade_answer
from app.services.question_support import QuestionGenerationUnavailable
from app.services.skill_mastery import MASTERY_POLICY, get_skill_mastery, get_student_mastery
from app.services.study_coach import (
    StudyCoachAction,
    StudyCoachLinks,
    StudyCoachResponse,
    generate_study_coach_guidance,
)

router = APIRouter(prefix="/learning")


class LearningProgressUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str = Field(min_length=1, max_length=100)
    lesson_id: str = Field(min_length=1, max_length=32)
    completed: bool


class PracticeSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str = Field(min_length=1, max_length=100)
    lesson_id: str = Field(min_length=1, max_length=32)


class PracticeAnswerSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=32)
    answer: str = Field(min_length=1, max_length=6000)

    @field_validator("answer")
    @classmethod
    def answer_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Answer cannot be blank.")
        return value


class AssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str = Field(min_length=1, max_length=100)
    lesson_id: str = Field(min_length=1, max_length=32)


class StudyCoachRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    skill_id: str = Field(min_length=1, max_length=100)
    lesson_id: str = Field(min_length=1, max_length=32)
    concept: str = Field(min_length=1, max_length=120)
    question: Optional[str] = Field(default=None, max_length=500)

    @field_validator("skill_id", "lesson_id", "concept")
    @classmethod
    def required_values_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("This value cannot be blank.")
        return value

    @field_validator("question")
    @classmethod
    def blank_question_is_omitted(cls, value: Optional[str]) -> Optional[str]:
        return value or None


def _get_latest_roadmap(db: Session, user_id: int) -> Optional[Roadmap]:
    return (
        db.query(Roadmap)
        .filter(Roadmap.user_id == user_id)
        .order_by(Roadmap.id.desc())
        .first()
    )


def _build_learning_context(
    db: Session,
    current_user: User,
    skill_id: str,
) -> dict:
    latest_gap_query = db.query(GapReport).filter(GapReport.user_id == current_user.id)
    if current_user.target_role:
        latest_gap_query = latest_gap_query.filter(GapReport.target_role == current_user.target_role)
    gap = latest_gap_query.order_by(GapReport.id.desc()).first()

    roadmap_context = None
    roadmap = _get_latest_roadmap(db, current_user.id)
    if roadmap and isinstance(roadmap.weeks, list):
        for week_index, week in enumerate(roadmap.weeks):
            if not isinstance(week, dict):
                continue
            tasks = week.get("tasks", [])
            if not isinstance(tasks, list):
                continue
            for task_index, task in enumerate(tasks):
                if not isinstance(task, dict) or map_roadmap_task_skill(task.get("task")) != skill_id:
                    continue
                task_text = task["task"]
                if "[REVISE" in task_text.upper():
                    study_type = "revision"
                elif "[LEARN" in task_text.upper():
                    study_type = "learning from scratch"
                else:
                    study_type = None
                roadmap_context = {
                    "week": week.get("week", week_index + 1),
                    "theme": week.get("theme"),
                    "task": task_text,
                    "study_type": study_type,
                    "priority_order": f"{week_index + 1}.{task_index + 1}",
                }
                break
            if roadmap_context:
                break

    gap_context = None
    if gap:
        covered = gap.covered_by_syllabus or []
        missing = gap.missing or []
        for entry in covered:
            if isinstance(entry, dict) and entry.get("skill") == skill_id:
                gap_context = {"category": "covered_by_syllabus", "status": entry.get("status")}
                break
        if gap_context is None and skill_id in (gap.from_resume or []):
            gap_context = {"category": "from_resume"}
        if gap_context is None:
            for entry in missing:
                if isinstance(entry, dict) and entry.get("skill") == skill_id:
                    gap_context = {"category": "missing", "status": entry.get("status")}
                    break

    target_role = current_user.target_role or (gap.target_role if gap else None)
    return {
        "target_role": target_role,
        "branch": current_user.branch,
        "semester": current_user.semester,
        "vtu_subjects": get_vtu_subjects(current_user.branch, current_user.semester, skill_id),
        "gap": gap_context,
        "roadmap": roadmap_context,
    }


def _course_response(course: LearningCourse) -> dict:
    lessons = course.content.get("lessons", [])
    completed = set(course.completed_lessons or [])
    return {
        "skill_id": course.skill_id,
        "context": course.context or {},
        "content": course.content,
        "completed_lessons": sorted(completed),
        "progress": {
            "completed": len(completed),
            "total": len(lessons),
        },
        "completion_notice": (
            "Lesson completion tracks your learning progress; it is not a measure or certification of skill mastery."
        ),
        "content_source": course.content.get("content_source", "llm"),
    }


def _public_question(question_data: dict) -> dict:
    question = PracticeQuestion.model_validate(question_data, context={"allow_legacy_mcq": True})
    return question.model_dump(
        exclude={"correct_answer", "accepted_keywords", "explanation", "reference_answer"}
    )


def _practice_response(
    practice_session: PracticeSession,
    db: Session,
) -> dict:
    attempts = (
        db.query(PracticeAttempt)
        .filter(
            PracticeAttempt.session_id == practice_session.id,
            PracticeAttempt.user_id == practice_session.user_id,
        )
        .order_by(PracticeAttempt.id.desc())
        .all()
    )
    latest_by_question = {}
    for attempt in attempts:
        if attempt.question_id not in latest_by_question:
            latest_by_question[attempt.question_id] = {
                "answer": attempt.answer,
                "is_correct": attempt.is_correct,
                "feedback": attempt.feedback,
                "explanation": attempt.explanation,
                "created_at": attempt.created_at.isoformat(),
            }
    return {
        "id": practice_session.id,
        "skill_id": practice_session.skill_id,
        "lesson_id": practice_session.lesson_id,
        "questions": [_public_question(question) for question in practice_session.questions],
        "attempts": latest_by_question,
        "content_source": practice_session.content_source,
        "created_at": practice_session.created_at.isoformat(),
    }


def _assessment_response(attempt: AssessmentAttempt) -> dict:
    submitted = attempt.result is not None
    questions = []
    for question in attempt.questions:
        public = {
            key: value
            for key, value in question.items()
            if key not in {"correct_answer", "explanation"}
        }
        if submitted:
            public["correct_answer"] = question["correct_answer"]
            public["explanation"] = question["explanation"]
        questions.append(public)
    return {
        "id": attempt.id,
        "skill_id": attempt.skill_id,
        "lesson_id": attempt.lesson_id,
        "questions": questions,
        "content_source": attempt.content_source,
        "submitted": submitted,
        "submitted_answers": attempt.submitted_answers if submitted else None,
        "result": attempt.result,
        "created_at": attempt.created_at.isoformat(),
        "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
    }


@router.post("/coach", response_model=StudyCoachResponse)
def ask_study_coach(
    request: StudyCoachRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    canonical_skill = get_canonical_skill(request.skill_id)
    if canonical_skill is None:
        raise HTTPException(status_code=404, detail="Unknown canonical skill identifier.")

    course = (
        db.query(LearningCourse)
        .filter(
            LearningCourse.user_id == current_user.id,
            LearningCourse.skill_id == canonical_skill,
        )
        .first()
    )
    if course is None:
        raise HTTPException(status_code=404, detail="Open the skill lesson before using the Study Coach.")

    raw_lessons = course.content.get("lessons", []) if isinstance(course.content, dict) else []
    raw_lesson = next(
        (
            item
            for item in raw_lessons
            if isinstance(item, dict) and item.get("lesson_id") == request.lesson_id
        ),
        None,
    ) if isinstance(raw_lessons, list) else None
    if raw_lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found for this skill.")
    try:
        lesson = LessonContent.model_validate(raw_lesson)
    except ValidationError as exc:
        raise HTTPException(
            status_code=409,
            detail="This lesson's stored content is unavailable for Study Coach grounding.",
        ) from exc

    mastery = get_skill_mastery(db, current_user.id, canonical_skill)
    semester = (
        current_user.semester
        if isinstance(current_user.semester, int) and 1 <= current_user.semester <= 12
        else None
    )
    guidance, source, evidence = generate_study_coach_guidance(
        skill_id=canonical_skill,
        lesson=lesson,
        concept=request.concept,
        question=request.question,
        vtu_subjects=get_vtu_subjects(
            current_user.branch,
            semester,
            canonical_skill,
        ),
        mastery=mastery,
    )

    encoded_skill = quote(canonical_skill, safe="")
    encoded_lesson = quote(lesson.lesson_id, safe="")
    action_data = {
        "method": "POST",
        "skill_id": canonical_skill,
        "lesson_id": lesson.lesson_id,
    }
    response = StudyCoachResponse(
        skill_id=canonical_skill,
        lesson_id=lesson.lesson_id,
        concept=request.concept,
        source=source,
        explanation=guidance.explanation,
        hints=guidance.hints,
        example=guidance.example,
        evidence=evidence,
        links=StudyCoachLinks(
            lesson=f"/learn?skill={encoded_skill}&lesson={encoded_lesson}",
            practice=StudyCoachAction(href="/learning/practice", **action_data),
            assessment=StudyCoachAction(href="/learning/assessment", **action_data),
        ),
    )
    return StudyCoachResponse.model_validate(response.model_dump())


@router.get("/roadmap-mappings")
def get_roadmap_mappings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    roadmap = _get_latest_roadmap(db, current_user.id)
    mappings = []
    if roadmap and isinstance(roadmap.weeks, list):
        for week_index, week in enumerate(roadmap.weeks):
            if not isinstance(week, dict):
                continue
            tasks = week.get("tasks", [])
            if not isinstance(tasks, list):
                continue
            for task_index, task in enumerate(tasks):
                if not isinstance(task, dict):
                    continue
                skill_id = map_roadmap_task_skill(task.get("task"))
                if skill_id:
                    mappings.append(
                        {
                            "week_index": week_index,
                            "task_index": task_index,
                            "skill_id": skill_id,
                        }
                    )
    return {"mappings": mappings}


@router.get("/skill")
def get_learning_course(
    skill_id: str = Query(min_length=1, max_length=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    canonical_skill = get_canonical_skill(skill_id)
    if canonical_skill is None:
        raise HTTPException(status_code=404, detail="Unknown canonical skill identifier.")

    course = (
        db.query(LearningCourse)
        .filter(
            LearningCourse.user_id == current_user.id,
            LearningCourse.skill_id == canonical_skill,
        )
        .first()
    )
    if course:
        return _course_response(course)

    context = _build_learning_context(db, current_user, canonical_skill)
    content, content_source = generate_learning_content(canonical_skill, context)
    content_data = content.model_dump()
    content_data["content_source"] = content_source
    course = LearningCourse(
        user_id=current_user.id,
        skill_id=canonical_skill,
        content=content_data,
        context=context,
        completed_lessons=[],
    )
    db.add(course)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        course = (
            db.query(LearningCourse)
            .filter(
                LearningCourse.user_id == current_user.id,
                LearningCourse.skill_id == canonical_skill,
            )
            .first()
        )
        if course is None:
            raise
    else:
        db.refresh(course)
    return _course_response(course)


@router.put("/progress")
def update_learning_progress(
    update: LearningProgressUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    canonical_skill = get_canonical_skill(update.skill_id)
    if canonical_skill is None:
        raise HTTPException(status_code=404, detail="Unknown canonical skill identifier.")

    course = (
        db.query(LearningCourse)
        .filter(
            LearningCourse.user_id == current_user.id,
            LearningCourse.skill_id == canonical_skill,
        )
        .first()
    )
    if course is None:
        raise HTTPException(status_code=404, detail="Learning course not found. Open the skill lesson first.")

    lesson_ids = {lesson.get("lesson_id") for lesson in course.content.get("lessons", [])}
    if update.lesson_id not in lesson_ids:
        raise HTTPException(status_code=404, detail="Lesson not found for this skill.")

    completed = set(course.completed_lessons or [])
    if update.completed:
        completed.add(update.lesson_id)
    else:
        completed.discard(update.lesson_id)
    course.completed_lessons = sorted(completed)
    flag_modified(course, "completed_lessons")
    db.commit()
    db.refresh(course)
    return _course_response(course)


@router.post("/practice")
def create_practice_session(
    request: PracticeSessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    canonical_skill = get_canonical_skill(request.skill_id)
    if canonical_skill is None:
        raise HTTPException(status_code=404, detail="Unknown canonical skill identifier.")

    course = (
        db.query(LearningCourse)
        .filter(
            LearningCourse.user_id == current_user.id,
            LearningCourse.skill_id == canonical_skill,
        )
        .first()
    )
    if course is None:
        raise HTTPException(status_code=404, detail="Open the skill lesson before starting practice.")

    lesson = next(
        (
            lesson
            for lesson in course.content.get("lessons", [])
            if lesson.get("lesson_id") == request.lesson_id
        ),
        None,
    )
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found for this skill.")

    try:
        questions, source = generate_practice_set(
            canonical_skill,
            lesson,
            course.context or {},
        )
    except QuestionGenerationUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    practice_session = PracticeSession(
        user_id=current_user.id,
        skill_id=canonical_skill,
        lesson_id=request.lesson_id,
        questions=[question.model_dump() for question in questions.questions],
        content_source=source,
    )
    db.add(practice_session)
    db.commit()
    db.refresh(practice_session)
    return _practice_response(practice_session, db)


@router.get("/practice/{session_id}")
def get_practice_session(
    session_id: int = Path(gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    practice_session = (
        db.query(PracticeSession)
        .filter(
            PracticeSession.id == session_id,
            PracticeSession.user_id == current_user.id,
        )
        .first()
    )
    if practice_session is None:
        raise HTTPException(status_code=404, detail="Practice session not found.")
    return _practice_response(practice_session, db)


@router.post("/practice/{session_id}/answers")
def submit_practice_answer(
    submission: PracticeAnswerSubmission,
    session_id: int = Path(gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    practice_session = (
        db.query(PracticeSession)
        .filter(
            PracticeSession.id == session_id,
            PracticeSession.user_id == current_user.id,
        )
        .first()
    )
    if practice_session is None:
        raise HTTPException(status_code=404, detail="Practice session not found.")

    question_data = next(
        (
            question
            for question in practice_session.questions
            if question.get("question_id") == submission.question_id
        ),
        None,
    )
    if question_data is None:
        raise HTTPException(status_code=404, detail="Question not found in this practice session.")
    try:
        grade = grade_answer(question_data, submission.answer)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    attempt = PracticeAttempt(
        user_id=current_user.id,
        session_id=practice_session.id,
        question_id=submission.question_id,
        answer=submission.answer,
        is_correct=grade.is_correct,
        feedback=grade.feedback,
        explanation=grade.explanation,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return {
        "question_id": attempt.question_id,
        "answer": attempt.answer,
        "is_correct": attempt.is_correct,
        "feedback": attempt.feedback,
        "explanation": attempt.explanation,
        "created_at": attempt.created_at.isoformat(),
    }


@router.post("/assessment")
def create_assessment(
    request: AssessmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    canonical_skill = get_canonical_skill(request.skill_id)
    if canonical_skill is None:
        raise HTTPException(status_code=404, detail="Unknown canonical skill identifier.")

    course = (
        db.query(LearningCourse)
        .filter(
            LearningCourse.user_id == current_user.id,
            LearningCourse.skill_id == canonical_skill,
        )
        .first()
    )
    if course is None:
        raise HTTPException(status_code=404, detail="Open the skill lesson before starting an assessment.")

    lesson = next(
        (
            lesson
            for lesson in course.content.get("lessons", [])
            if lesson.get("lesson_id") == request.lesson_id
        ),
        None,
    )
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found for this skill.")

    try:
        questions, source = generate_assessment(canonical_skill, lesson, course.context or {})
    except QuestionGenerationUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    assessment = AssessmentAttempt(
        user_id=current_user.id,
        skill_id=canonical_skill,
        lesson_id=request.lesson_id,
        questions=[question.model_dump() for question in questions.questions],
        content_source=source,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return _assessment_response(assessment)


@router.get("/assessment/{assessment_id}")
def get_assessment(
    assessment_id: int = Path(gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assessment = (
        db.query(AssessmentAttempt)
        .filter(
            AssessmentAttempt.id == assessment_id,
            AssessmentAttempt.user_id == current_user.id,
        )
        .first()
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment attempt not found.")
    return _assessment_response(assessment)


@router.post("/assessment/{assessment_id}/submit")
def submit_assessment(
    submission: AssessmentSubmission,
    assessment_id: int = Path(gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assessment = (
        db.query(AssessmentAttempt)
        .filter(
            AssessmentAttempt.id == assessment_id,
            AssessmentAttempt.user_id == current_user.id,
        )
        .first()
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment attempt not found.")
    if assessment.result is not None:
        raise HTTPException(status_code=409, detail="This assessment has already been submitted.")

    submitted_answers = {
        answer.question_id: answer.answer
        for answer in submission.answers
    }
    try:
        result = score_assessment(assessment.questions, submitted_answers)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    assessment.submitted_answers = submitted_answers
    assessment.result = result
    assessment.submitted_at = datetime.utcnow()
    db.commit()
    db.refresh(assessment)
    return _assessment_response(assessment)


@router.get("/mastery")
def get_mastery_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {
        "skills": get_student_mastery(db, current_user.id),
        "policy": MASTERY_POLICY,
        "notice": (
            "Mastery status is based only on your submitted assessment evidence. "
            "It does not affect placement readiness."
        ),
    }


@router.get("/mastery/{skill_id}")
def get_mastery_for_skill(
    skill_id: str = Path(min_length=1, max_length=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    canonical_skill = get_canonical_skill(skill_id)
    if canonical_skill is None:
        raise HTTPException(status_code=404, detail="Unknown canonical skill identifier.")
    return get_skill_mastery(db, current_user.id, canonical_skill)


@router.get("/recommendations")
def get_adaptive_recommendations(
    skill_id: Optional[str] = Query(default=None, min_length=1, max_length=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    canonical_skill = None
    if skill_id is not None:
        canonical_skill = get_canonical_skill(skill_id)
        if canonical_skill is None:
            raise HTTPException(status_code=404, detail="Unknown canonical skill identifier.")
    return get_recommendations(db, current_user, requested_skill=canonical_skill)
