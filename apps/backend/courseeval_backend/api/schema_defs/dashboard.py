from typing import List

from pydantic import BaseModel


class ClassRanking(BaseModel):
    class_id: int
    class_name: str
    avg_score: float
    rank: int


class DashboardStats(BaseModel):
    total_students: int
    total_classes: int
    total_scores: int = 0
    avg_score: float
    attendance_rate: float = 0.0
    recent_scores: List["ScoreResponse"] = []
    class_rankings: List[ClassRanking] = []


class StudentRanking(BaseModel):
    student_id: int
    student_name: str
    class_name: str
    avg_score: float
    rank: int
