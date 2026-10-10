from datetime import datetime
import math
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import get_current_admin, get_current_user
from app.config import settings
from app.database import get_db
from app.models import (
    AssessmentAttempt,
    GapReport,
    InterviewSession,
    PremiumAccessRequest,
    PremiumSubscription,
    ReadinessScore,
    ReadinessScoreHistory,
    Resume,
    Roadmap,
    User,
)
from app.services.skill_mastery import get_student_mastery
from app.services.adaptive_recommendations import get_recommendations
from app.services import premium_payments

router = APIRouter(prefix="/premium")


def _get_active_premium_subscription(db: Session, user_id: int) -> PremiumSubscription | None:
    subscription = (
        db.query(PremiumSubscription)
        .filter(PremiumSubscription.user_id == user_id)
        .first()
    )
    if subscription and subscription.plan == "premium" and subscription.status == "active":
        return subscription
    return None


def _plan_response(db: Session, user: User) -> dict:
    subscription = _get_active_premium_subscription(db, user.id)
    pending_request = (
        db.query(PremiumAccessRequest)
        .filter(
            PremiumAccessRequest.user_id == user.id,
            PremiumAccessRequest.status == "pending",
        )
        .order_by(PremiumAccessRequest.id.desc())
        .first()
    )
    return {
        "plan": "premium" if subscription else "free",
        "entitlement_status": "active" if subscription else "inactive",
        "access_request_pending": pending_request is not None,
        "pricing": {
            "display": settings.PREMIUM_PRICE_DISPLAY,
            "billing_period": settings.PREMIUM_BILLING_PERIOD_DISPLAY,
            **premium_payments.checkout_configuration(),
            "payment_provider_configured": premium_payments.checkout_configuration()[
                "checkout_enabled"
            ],
        },
    }


def _interview_feedback(session: InterviewSession) -> list[dict]:
    feedback_fields = (
        "strengths",
        "missing_points",
        "improvement_suggestions",
        "feedback",
        "explanation",
    )
    feedback = []
    for score in session.scores or []:
        if not isinstance(score, dict):
            continue
        question_index = score.get("question_index")
        if (
            not isinstance(question_index, int)
            or isinstance(question_index, bool)
            or question_index < 0
        ):
            continue
        item = {"question_index": question_index}
        for field in ("question_type", "evaluation_source"):
            value = score.get(field)
            if isinstance(value, str):
                item[field] = value
        value = score.get("score_out_of_10")
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            item["score_out_of_10"] = value
        value = score.get("is_correct")
        if isinstance(value, bool):
            item["is_correct"] = value
        for field in feedback_fields:
            value = score.get(field)
            if isinstance(value, str):
                item[field] = value
        feedback.append(item)
    return feedback


@router.get("/plan")
def get_premium_plan(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _plan_response(db, current_user)


def _payment_http_error(error: premium_payments.PaymentError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=str(error))


@router.post("/payment/orders", status_code=201)
def create_premium_payment_order(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return premium_payments.create_order(db, current_user)
    except premium_payments.PaymentError as error:
        raise _payment_http_error(error) from error


class PaymentVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    razorpay_order_id: str = Field(min_length=1, max_length=64)
    razorpay_payment_id: str = Field(min_length=1, max_length=64)
    razorpay_signature: str = Field(pattern=r"^[a-fA-F0-9]{64}$")


@router.post("/payment/verify")
def verify_premium_payment(
    verification: PaymentVerification,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return premium_payments.verify_payment(
            db,
            current_user,
            verification.razorpay_order_id,
            verification.razorpay_payment_id,
            verification.razorpay_signature,
        )
    except premium_payments.PaymentError as error:
        raise _payment_http_error(error) from error


@router.get("/payment/orders/{payment_order_id}")
def get_premium_payment_status(
    payment_order_id: int = Path(gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return premium_payments.payment_status(db, current_user, payment_order_id)
    except premium_payments.PaymentError as error:
        raise _payment_http_error(error) from error


@router.post("/payment/webhook")
async def razorpay_premium_webhook(
    request: Request,
    signature: str = Header(default="", alias="X-Razorpay-Signature"),
    event_id: str = Header(default="", alias="x-razorpay-event-id", max_length=128),
    db: Session = Depends(get_db),
):
    raw_body = await request.body()
    try:
        return premium_payments.process_webhook(
            db,
            raw_body,
            signature,
            event_id,
        )
    except premium_payments.PaymentError as error:
        raise _payment_http_error(error) from error


@router.post("/access-request", status_code=201)
def request_premium_access(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if _get_active_premium_subscription(db, current_user.id):
        return {
            "status": "already_active",
            "message": "Premium access is already active for this account.",
            **_plan_response(db, current_user),
        }

    existing_request = (
        db.query(PremiumAccessRequest)
        .filter(
            PremiumAccessRequest.user_id == current_user.id,
            PremiumAccessRequest.status == "pending",
        )
        .first()
    )
    if existing_request is None:
        db.add(PremiumAccessRequest(user_id=current_user.id, status="pending"))
        db.commit()

    return {
        "status": "request_recorded",
        "message": (
            "Your demo access request was recorded. No payment was taken and "
            "Premium access has not been activated."
        ),
        **_plan_response(db, current_user),
    }


class EntitlementUpdate(BaseModel):
    active: bool


@router.put("/admin/users/{user_id}/entitlement")
def set_manual_entitlement(
    update: EntitlementUpdate,
    user_id: int = Path(gt=0),
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    subscription = (
        db.query(PremiumSubscription)
        .filter(PremiumSubscription.user_id == user_id)
        .first()
    )
    if subscription is None:
        subscription = PremiumSubscription(user_id=user_id)
        db.add(subscription)

    subscription.plan = "premium" if update.active else "free"
    subscription.status = "active" if update.active else "inactive"
    subscription.updated_at = datetime.utcnow()
    pending_requests = (
        db.query(PremiumAccessRequest)
        .filter(
            PremiumAccessRequest.user_id == user_id,
            PremiumAccessRequest.status == "pending",
        )
        .all()
    )
    for request in pending_requests:
        request.status = "reviewed"
    db.commit()
    return {
        "user_id": user_id,
        "plan": subscription.plan,
        "entitlement_status": subscription.status,
        "updated_by_admin_id": current_admin.id,
        "notice": "This is a manually provisioned entitlement, not a payment confirmation.",
    }


@router.get("/overview")
def get_premium_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if _get_active_premium_subscription(db, current_user.id) is None:
        raise HTTPException(
            status_code=403,
            detail="Premium analytics and placement reports require active Premium access.",
        )

    user_id = current_user.id
    resume = (
        db.query(Resume)
        .filter(Resume.user_id == user_id)
        .order_by(Resume.id.desc())
        .first()
    )
    gap = (
        db.query(GapReport)
        .filter(GapReport.user_id == user_id)
        .order_by(GapReport.id.desc())
        .first()
    )
    roadmap = (
        db.query(Roadmap)
        .filter(Roadmap.user_id == user_id)
        .order_by(Roadmap.id.desc())
        .first()
    )
    interview = (
        db.query(InterviewSession)
        .filter(InterviewSession.user_id == user_id)
        .order_by(InterviewSession.id.desc())
        .first()
    )
    readiness = (
        db.query(ReadinessScore)
        .filter(ReadinessScore.user_id == user_id)
        .order_by(ReadinessScore.id.desc())
        .first()
    )
    readiness_history = (
        db.query(ReadinessScoreHistory)
        .filter(ReadinessScoreHistory.user_id == user_id)
        .order_by(ReadinessScoreHistory.created_at.asc(), ReadinessScoreHistory.id.asc())
        .all()
    )
    submitted_assessments = (
        db.query(AssessmentAttempt)
        .filter(
            AssessmentAttempt.user_id == user_id,
            AssessmentAttempt.result.is_not(None),
        )
        .order_by(AssessmentAttempt.submitted_at.asc(), AssessmentAttempt.id.asc())
        .all()
    )

    total_correct = 0
    total_questions = 0
    for attempt in submitted_assessments:
        result = attempt.result or {}
        if isinstance(result, dict):
            total_correct += max(0, int(result.get("correct") or 0))
            total_questions += max(0, int(result.get("total") or 0))

    roadmap_tasks = []
    roadmap_week_count = 0
    if roadmap and isinstance(roadmap.weeks, list):
        roadmap_week_count = len(roadmap.weeks)
        for week_index, week in enumerate(roadmap.weeks, start=1):
            if not isinstance(week, dict) or not isinstance(week.get("tasks"), list):
                continue
            for task in week["tasks"]:
                if isinstance(task, dict):
                    roadmap_tasks.append({
                        "week": week.get("week", week_index),
                        "task": task.get("task", ""),
                        "completed": bool(task.get("completed")),
                    })

    resume_projects = resume.projects if resume and isinstance(resume.projects, list) else []
    resume_skills = resume.extracted_skills if resume and isinstance(resume.extracted_skills, list) else []
    mastery = get_student_mastery(db, user_id)
    recommendations = get_recommendations(db, current_user)
    return {
        "plan": _plan_response(db, current_user),
        "analytics": {
            "readiness_current": (
                {
                    "total": readiness.total,
                    "resume_score": readiness.resume_score,
                    "skill_score": readiness.skill_score,
                    "roadmap_score": readiness.roadmap_score,
                    "interview_score": readiness.interview_score,
                }
                if readiness
                else None
            ),
            "readiness_history": [
                {
                    "created_at": item.created_at,
                    "total": item.total,
                }
                for item in readiness_history
            ],
            "roadmap_progress": (
                {
                    "completed_tasks": sum(1 for task in roadmap_tasks if task["completed"]),
                    "total_tasks": len(roadmap_tasks),
                    "weeks": roadmap_week_count,
                }
                if roadmap
                else None
            ),
            "assessment_accuracy": (
                {
                    "assessments": len(submitted_assessments),
                    "correct": total_correct,
                    "questions": total_questions,
                    "accuracy_pct": round(total_correct / total_questions * 100, 1),
                }
                if total_questions
                else None
            ),
            "skill_mastery": mastery,
            "recommendations": recommendations["recommendations"],
            "recommendation_notice": recommendations["notice"],
        },
        "placement_report": {
            "target_role": current_user.target_role or (gap.target_role if gap else None),
            "resume": (
                {
                    "ats_score": resume.ats_score,
                    "skills": resume_skills,
                    "projects": resume_projects,
                }
                if resume
                else None
            ),
            "skill_gap": (
                {
                    "match_pct": gap.skill_match_pct,
                    "covered_by_syllabus": gap.covered_by_syllabus or [],
                    "from_resume": gap.from_resume or [],
                    "missing": gap.missing or [],
                }
                if gap
                else None
            ),
            "roadmap": roadmap_tasks if roadmap else None,
            "latest_interview": (
                {
                    "target_role": interview.target_role,
                    "created_at": interview.created_at,
                    "overall_score": interview.overall_score,
                    "weak_skills": interview.weak_skills or [],
                    "feedback": _interview_feedback(interview),
                    "completed": bool(interview.scores)
                    and len(interview.scores) >= len(interview.questions or []),
                }
                if interview
                else None
            ),
        },
        "notice": (
            "Scores and progress are measured from your stored records. Skill mastery "
            "uses submitted assessment evidence only. Recommendations are not generated "
            "by this report and no readiness formula is changed."
        ),
    }
