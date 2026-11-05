from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.config import settings

# 1. Import every router we created
from app.routers import (
    auth_router, 
    resume_router, 
    gap_router, 
    roadmap_router, 
    dashboard_router, 
    interview_router,
    readiness_router,
    learning_router,
    premium_router,
    placement_router,
)

# Initialize database tables
Base.metadata.create_all(bind=engine)
import os
from app.database import SessionLocal
from app.models import User
from app.auth import PLACEMENT_STAFF_ROLE, get_password_hash

def ensure_placement_head():
    email = os.getenv("HEAD_EMAIL")
    password = os.getenv("HEAD_PASSWORD")
    if not email or not password:
        return
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            db.add(User(
                name="Placement Head",
                email=email,
                hashed_password=get_password_hash(password),
                role=PLACEMENT_STAFF_ROLE,
            ))
        else:
            user.role = PLACEMENT_STAFF_ROLE
        db.commit()
    finally:
        db.close()

ensure_placement_head()

app = FastAPI(title="PlaceIQ API")

# Configure CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Register every route explicitly
app.include_router(auth_router.router, tags=["Authentication"])
app.include_router(resume_router.router, tags=["Resume Engine"])
app.include_router(gap_router.router, tags=["VTU Gap Analyzer"])
app.include_router(roadmap_router.router, tags=["AI Roadmap"])
app.include_router(dashboard_router.router, tags=["Dashboard"])
app.include_router(interview_router.router, tags=["Mock Interview"])
app.include_router(readiness_router.router, tags=["Readiness Score"])
app.include_router(learning_router.router, tags=["Skill Learning"])
app.include_router(premium_router.router, tags=["Premium Plan"])
app.include_router(placement_router.router, tags=["Placement Cell"])

@app.get("/")
def health_check():
    return {"status": "ok", "message": "PlaceIQ Backend is running"}