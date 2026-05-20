"""Class-scope query helpers shared by course-adjacent routers."""

from __future__ import annotations

from typing import List

from sqlalchemy import false as sql_false
from sqlalchemy.orm import Query, Session

from apps.backend.courseeval_backend.db.models import Class, User, UserRole
from apps.backend.courseeval_backend.domains.courses.access import get_accessible_class_ids_from_courses


def apply_class_id_filter(query: Query, column, class_ids: List[int]) -> Query:
    """Avoid SQL errors from IN () when the caller has no accessible classes."""
    if not class_ids:
        return query.filter(sql_false())
    return query.filter(column.in_(class_ids))


def get_accessible_class_ids(user: User, db: Session) -> List[int]:
    if user.role == UserRole.ADMIN:
        return [class_obj.id for class_obj in db.query(Class).all()]
    return get_accessible_class_ids_from_courses(user, db)
