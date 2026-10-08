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
    interview_router
)

# Initialize database tables
Base.metadata.create_all(bind=engine)

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

@app.get("/")
def health_check():
    return {"status": "ok", "message": "PlaceIQ Backend is running"}