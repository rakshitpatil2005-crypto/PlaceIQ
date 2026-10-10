from sqlalchemy import (
    Column, Integer, String, Float, JSON, DateTime, ForeignKey, UniqueConstraint,
    Index, text,
)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

from sqlalchemy import Column, Integer, String, Boolean
from app.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="student") # 'student' or 'admin'
    branch = Column(String, nullable=True)
    semester = Column(Integer, nullable=True)
    target_role = Column(String, nullable=True)

class Resume(Base):
    __tablename__ = "resumes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    filename = Column(String)
    raw_text = Column(String)
    extracted_skills = Column(JSON)
    projects = Column(JSON)
    ats_score = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

class GapReport(Base):
    __tablename__ = "gap_reports"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    target_role = Column(String)
    covered_by_syllabus = Column(JSON)
    from_resume = Column(JSON)
    missing = Column(JSON)
    skill_match_pct = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

class Roadmap(Base):
    __tablename__ = "roadmaps"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    weeks = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    target_role = Column(String)
    questions = Column(JSON)
    answers = Column(JSON)
    scores = Column(JSON)
    overall_score = Column(Float, nullable=True)
    weak_skills = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

class ReadinessScore(Base):
    __tablename__ = "readiness_scores"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    resume_score = Column(Float, default=0)
    skill_score = Column(Float, default=0)
    roadmap_score = Column(Float, default=0)
    interview_score = Column(Float, default=0)
    total = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReadinessScoreHistory(Base):
    __tablename__ = "readiness_score_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    resume_score = Column(Float, default=0)
    skill_score = Column(Float, default=0)
    roadmap_score = Column(Float, default=0)
    interview_score = Column(Float, default=0)
    total = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class LearningCourse(Base):
    __tablename__ = "learning_courses"
    __table_args__ = (UniqueConstraint("user_id", "skill_id", name="uq_learning_course_user_skill"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    skill_id = Column(String, nullable=False, index=True)
    content = Column(JSON, nullable=False)
    context = Column(JSON, nullable=False)
    completed_lessons = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PracticeSession(Base):
    __tablename__ = "practice_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    skill_id = Column(String, nullable=False, index=True)
    lesson_id = Column(String, nullable=False)
    questions = Column(JSON, nullable=False)
    content_source = Column(String, nullable=False, default="llm")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PracticeAttempt(Base):
    __tablename__ = "practice_attempts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("practice_sessions.id"), nullable=False, index=True)
    question_id = Column(String, nullable=False, index=True)
    answer = Column(String, nullable=False)
    is_correct = Column(Boolean, nullable=False)
    feedback = Column(String, nullable=False)
    explanation = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AssessmentAttempt(Base):
    __tablename__ = "assessment_attempts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    skill_id = Column(String, nullable=False, index=True)
    lesson_id = Column(String, nullable=False)
    questions = Column(JSON, nullable=False)
    content_source = Column(String, nullable=False, default="llm")
    submitted_answers = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PremiumSubscription(Base):
    __tablename__ = "premium_subscriptions"
    __table_args__ = (UniqueConstraint("user_id", name="uq_premium_subscription_user"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    plan = Column(String, nullable=False, default="free")
    status = Column(String, nullable=False, default="inactive")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PremiumAccessRequest(Base):
    __tablename__ = "premium_access_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PremiumPaymentOrder(Base):
    __tablename__ = "premium_payment_orders"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_premium_payment_order_idempotency"),
        UniqueConstraint("receipt", name="uq_premium_payment_order_receipt"),
        UniqueConstraint("razorpay_order_id", name="uq_premium_payment_order_provider_id"),
        Index(
            "uq_premium_payment_order_open_user",
            "user_id",
            unique=True,
            sqlite_where=text("status IN ('creating', 'creation_unknown', 'created')"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    idempotency_key = Column(String(64), nullable=False)
    receipt = Column(String(40), nullable=False)
    razorpay_order_id = Column(String(64), nullable=True)
    amount = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False)
    status = Column(String(24), nullable=False, default="creating")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PremiumPaymentAttempt(Base):
    __tablename__ = "premium_payment_attempts"
    __table_args__ = (
        UniqueConstraint("razorpay_payment_id", name="uq_premium_payment_attempt_provider_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(
        Integer,
        ForeignKey("premium_payment_orders.id"),
        nullable=False,
        index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    razorpay_payment_id = Column(String(64), nullable=False)
    amount = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False)
    status = Column(String(24), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PremiumPaymentWebhookEvent(Base):
    __tablename__ = "premium_payment_webhook_events"
    __table_args__ = (
        UniqueConstraint("provider_event_id", name="uq_premium_webhook_provider_event"),
    )

    id = Column(Integer, primary_key=True, index=True)
    provider_event_id = Column(String(128), nullable=False)
    event_type = Column(String(64), nullable=False)
    processed_at = Column(DateTime, default=datetime.utcnow, nullable=False)