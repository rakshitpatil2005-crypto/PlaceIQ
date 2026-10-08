from app.database import SessionLocal, engine, Base
from app.models import User
from app.auth import get_password_hash

def seed_users():
    db = SessionLocal()
    
    # Create an admin
    if not db.query(User).filter(User.email == "admin@placeiq.com").first():
        db.add(User(
            name="Placement Admin",
            email="admin@placeiq.com",
            password_hash=get_password_hash("admin123"),
            role="admin"
        ))
        
    # Create a test engineering student profile ready for VTU mapping
    if not db.query(User).filter(User.email == "samith@placeiq.com").first():
        db.add(User(
            name="Samith Ramachandra",
            email="samith@placeiq.com",
            password_hash=get_password_hash("student123"),
            role="student",
            branch="ECE",
            semester=7,
            target_role="Embedded Systems Engineer"
        ))
        
    db.commit()
    print("✅ Database seeded with default Admin and ECE Student profiles.")
    db.close()

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    seed_users()