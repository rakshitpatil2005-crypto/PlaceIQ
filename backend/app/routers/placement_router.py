from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_placement_staff
from app.database import get_db
from app.models import User
from app.services.placement_analytics import (
    get_cohort_summary,
    get_student_detail,
    get_student_page,
)

router = APIRouter(prefix="/placement")


def _filters(
    branch: str | None,
    semester: int | None,
    target_role: str | None,
) -> tuple[str | None, int | None, str | None]:
    return (
        branch.strip() if branch and branch.strip() else None,
        semester,
        target_role.strip() if target_role and target_role.strip() else None,
    )


@router.get("/dashboard")
def placement_dashboard(
    branch: str | None = Query(default=None, max_length=100),
    semester: int | None = Query(default=None, ge=1, le=12),
    target_role: str | None = Query(default=None, max_length=120),
    current_staff: User = Depends(get_current_placement_staff),
    db: Session = Depends(get_db),
):
    del current_staff
    filters = _filters(branch, semester, target_role)
    return get_cohort_summary(db, *filters)


@router.get("/students")
def placement_students(
    branch: str | None = Query(default=None, max_length=100),
    semester: int | None = Query(default=None, ge=1, le=12),
    target_role: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    sort_by: Literal["name", "branch", "semester", "readiness"] = "name",
    sort_order: Literal["asc", "desc"] = "asc",
    current_staff: User = Depends(get_current_placement_staff),
    db: Session = Depends(get_db),
):
    del current_staff
    filters = _filters(branch, semester, target_role)
    return get_student_page(
        db,
        *filters,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/students/{student_id}")
def placement_student_detail(
    student_id: int,
    current_staff: User = Depends(get_current_placement_staff),
    db: Session = Depends(get_db),
):
    del current_staff
    result = get_student_detail(db, student_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Student not found.")
    return result
