from apps.backend.courseeval_backend.db.models import User, UserRole


def is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def is_class_teacher(user: User) -> bool:
    return user.role == UserRole.CLASS_TEACHER


def is_teacher(user: User) -> bool:
    return user.role == UserRole.TEACHER


def is_student(user: User) -> bool:
    return user.role == UserRole.STUDENT


def is_admin_or_class_teacher(user: User) -> bool:
    return user.role in [UserRole.ADMIN, UserRole.CLASS_TEACHER]


def can_manage_students(user: User) -> bool:
    return user.role in [UserRole.ADMIN, UserRole.CLASS_TEACHER, UserRole.TEACHER]


def can_manage_scores(user: User) -> bool:
    return user.role in [UserRole.ADMIN, UserRole.CLASS_TEACHER, UserRole.TEACHER]


def can_manage_attendance(user: User) -> bool:
    return user.role in [UserRole.ADMIN, UserRole.CLASS_TEACHER, UserRole.TEACHER]


def can_manage_classes(user: User) -> bool:
    return user.role == UserRole.ADMIN


def can_manage_users(user: User) -> bool:
    return user.role == UserRole.ADMIN


def can_view_all_data(user: User) -> bool:
    return user.role == UserRole.ADMIN


def can_manage_teachers(user: User) -> bool:
    return user.role == UserRole.ADMIN
