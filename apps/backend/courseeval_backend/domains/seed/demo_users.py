"""User and roster builders for the default demo seed bundle."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from apps.backend.courseeval_backend.core.auth import get_password_hash
from apps.backend.courseeval_backend.db.models import Class, Student, User, UserRole

DEMO_PASSWORD = "111111"
DEMO_CLASS_NAME = "人工智能1班"
DEMO_TEACHER_DISPLAY_NAME = "李演示"
TEACHER_PRO_USERNAME = "teacher_pro"
TEACHER_PRO_PASSWORD = "teacher_pro"
TEACHER_PRO_DISPLAY_NAME = "王概率（演示）"

DEMO_STUDENT_SPECS = (
    ("stu1", "学生一", "13800001001"),
    ("stu2", "学生二", "13800001002"),
    ("stu3", "学生三", "13800001003"),
    ("stu4", "学生四", "13800001004"),
    ("stu5", "学生五", "13800001005"),
)


@dataclass(frozen=True)
class DemoRosterContext:
    teacher: User
    teacher_pro: User
    klass: Class


def ensure_demo_roster_context(db: Session) -> DemoRosterContext:
    """Ensure demo teacher accounts, class, student users, and roster rows."""

    pwd_hash = get_password_hash(DEMO_PASSWORD)

    teacher = db.query(User).filter(User.username == "teacher").first()
    if not teacher:
        teacher = User(
            username="teacher",
            hashed_password=pwd_hash,
            real_name=DEMO_TEACHER_DISPLAY_NAME,
            role=UserRole.TEACHER.value,
            class_id=None,
            is_active=True,
        )
        db.add(teacher)
        db.flush()
        print("Created demo teacher 'teacher'.")
    else:
        print("Demo teacher 'teacher' already exists.")
    teacher.real_name = DEMO_TEACHER_DISPLAY_NAME

    teacher_pro_hash = get_password_hash(TEACHER_PRO_PASSWORD)
    teacher_pro = db.query(User).filter(User.username == TEACHER_PRO_USERNAME).first()
    if not teacher_pro:
        teacher_pro = User(
            username=TEACHER_PRO_USERNAME,
            hashed_password=teacher_pro_hash,
            real_name=TEACHER_PRO_DISPLAY_NAME,
            role=UserRole.TEACHER.value,
            class_id=None,
            is_active=True,
        )
        db.add(teacher_pro)
        db.flush()
        print(f"Created demo teacher '{TEACHER_PRO_USERNAME}'.")
    else:
        if teacher_pro.role != UserRole.TEACHER.value:
            teacher_pro.role = UserRole.TEACHER.value
        teacher_pro.hashed_password = teacher_pro_hash
        teacher_pro.real_name = TEACHER_PRO_DISPLAY_NAME
        teacher_pro.class_id = None
        teacher_pro.is_active = True
        print(f"Demo teacher '{TEACHER_PRO_USERNAME}' already exists; refreshed password/display fields.")

    klass = db.query(Class).filter(Class.name == DEMO_CLASS_NAME).first()
    if not klass:
        klass = Class(name=DEMO_CLASS_NAME, grade=2026)
        db.add(klass)
        db.flush()
        print(f"Created demo class '{DEMO_CLASS_NAME}'.")
    else:
        print(f"Demo class '{DEMO_CLASS_NAME}' already exists.")

    for uname, display, phone in DEMO_STUDENT_SPECS:
        user = db.query(User).filter(User.username == uname).first()
        if not user:
            user = User(
                username=uname,
                hashed_password=pwd_hash,
                real_name=display,
                role=UserRole.STUDENT.value,
                class_id=klass.id,
                is_active=True,
            )
            db.add(user)
            db.flush()
            print(f"Created demo student user '{uname}'.")
        else:
            if user.role != UserRole.STUDENT.value:
                user.role = UserRole.STUDENT.value
            if user.class_id != klass.id or not user.is_active:
                user.class_id = klass.id
                user.is_active = True
            user.hashed_password = pwd_hash

        student = db.query(Student).filter(Student.student_no == uname, Student.class_id == klass.id).first()
        if not student:
            db.add(
                Student(
                    name=display,
                    student_no=uname,
                    class_id=klass.id,
                    teacher_id=teacher.id,
                    phone=phone,
                )
            )
            print(f"Created roster row for '{uname}'.")
        else:
            student.teacher_id = teacher.id
            student.phone = phone
            if (student.name or "") != display:
                student.name = display

    return DemoRosterContext(teacher=teacher, teacher_pro=teacher_pro, klass=klass)
