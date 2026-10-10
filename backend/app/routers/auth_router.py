from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from app.database import get_db
from app.models import User
from app.auth import (
    PLACEMENT_STAFF_ROLE,
    get_current_admin,
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
)

router = APIRouter(prefix="/auth")

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    branch: str = None
    semester: int = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class ProfileUpdate(BaseModel):
    branch: str
    semester: int
    target_role: str


class PlacementStaffUpdate(BaseModel):
    active: bool

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
        
    new_user = User(
        name=user_data.name,
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        branch=user_data.branch,
        semester=user_data.semester,
        role="student"
    )
    db.add(new_user)
    db.commit()
    return {"message": "User registered successfully"}

@router.post("/login")
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == credentials.email).first()
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "name": current_user.name, "email": current_user.email, "role": current_user.role, "branch": current_user.branch, "semester": current_user.semester, "target_role": current_user.target_role}

@router.put("/me/profile")
def update_profile(profile_data: ProfileUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.branch = profile_data.branch
    current_user.semester = profile_data.semester
    current_user.target_role = profile_data.target_role
    db.commit()
    return {"message": "Profile updated successfully"}


@router.put("/admin/users/{user_id}/placement-staff")
def set_placement_staff_access(
    update: PlacementStaffUpdate,
    user_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role not in ("student", PLACEMENT_STAFF_ROLE):
        raise HTTPException(
            status_code=409,
            detail="Placement staff access can only be changed for student accounts.",
        )

    user.role = PLACEMENT_STAFF_ROLE if update.active else "student"
    db.commit()
    return {
        "user_id": user.id,
        "role": user.role,
        "updated_by_admin_id": current_admin.id,
    }
