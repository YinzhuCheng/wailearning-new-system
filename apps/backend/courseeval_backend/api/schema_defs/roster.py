from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CourseEnrollmentResponse(BaseModel):
    id: int
    subject_id: int
    student_id: int
    class_id: int
    enrollment_type: str = "required"
    can_remove: bool
    created_at: datetime
    student_name: Optional[str] = None
    student_no: Optional[str] = None
    class_name: Optional[str] = None
    student_user_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class CourseRosterStudentInput(BaseModel):
    name: str
    student_no: str
    gender: Optional["Gender"] = None
    enrollment_type: Optional[str] = None
    phone: Optional[str] = None
    parent_phone: Optional[str] = None
    address: Optional[str] = None


class CourseEnrollmentTypeUpdate(BaseModel):
    enrollment_type: str
