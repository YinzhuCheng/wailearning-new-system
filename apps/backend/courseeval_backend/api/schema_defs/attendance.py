from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    LEAVE = "leave"


class AttendanceBase(BaseModel):
    student_id: int
    class_id: int
    subject_id: Optional[int] = None
    date: str
    status: AttendanceStatus
    remark: Optional[str] = None


class AttendanceCreate(AttendanceBase):
    pass


class AttendanceUpdate(BaseModel):
    status: Optional[AttendanceStatus] = None
    remark: Optional[str] = None


class AttendanceResponse(AttendanceBase):
    id: int
    student_name: Optional[str] = None
    class_name: Optional[str] = None
    subject_name: Optional[str] = None
    date: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AttendanceListResponse(BaseModel):
    total: int
    data: List[AttendanceResponse]
