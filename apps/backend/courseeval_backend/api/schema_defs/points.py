from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class PointRuleBase(BaseModel):
    name: str
    description: Optional[str] = None
    category: str
    points: int
    condition_type: str
    condition_value: Optional[str] = None


class PointRuleCreate(PointRuleBase):
    pass


class PointRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    points: Optional[int] = None
    condition_type: Optional[str] = None
    condition_value: Optional[str] = None
    is_active: Optional[bool] = None


class PointRuleResponse(PointRuleBase):
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StudentPointResponse(BaseModel):
    id: int
    student_id: int
    total_points: int
    available_points: int
    total_earned: int
    total_spent: int
    student_name: Optional[str] = None
    class_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PointRecordResponse(BaseModel):
    id: int
    student_id: int
    rule_id: Optional[int] = None
    points: int
    balance_after: int
    source_type: str
    source_id: Optional[int] = None
    description: Optional[str] = None
    operator_name: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PointRecordListResponse(BaseModel):
    total: int
    data: List[PointRecordResponse]


class PointItemBase(BaseModel):
    name: str
    description: Optional[str] = None
    item_type: str
    points_cost: int
    stock: int = -1
    image_url: Optional[str] = None


class PointItemCreate(PointItemBase):
    pass


class PointItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    item_type: Optional[str] = None
    points_cost: Optional[int] = None
    stock: Optional[int] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None


class PointItemResponse(PointItemBase):
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PointExchangeResponse(BaseModel):
    id: int
    student_id: int
    item_id: int
    points_spent: int
    quantity: int
    status: str
    exchange_time: datetime
    pickup_time: Optional[datetime] = None
    operator_name: Optional[str] = None
    remark: Optional[str] = None
    student_name: Optional[str] = None
    item_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PointExchangeListResponse(BaseModel):
    total: int
    data: List[PointExchangeResponse]


class PointAddRequest(BaseModel):
    student_id: int
    points: int
    description: str
    source_type: str = "manual"
    source_id: Optional[int] = None
    rule_id: Optional[int] = None


class PointExchangeRequest(BaseModel):
    item_id: int
    quantity: int = 1
    student_id: Optional[int] = None


class PointRankingResponse(BaseModel):
    student_id: int
    student_name: str
    class_name: str
    total_points: int
    rank: int


class PointStatsResponse(BaseModel):
    total_students: int
    active_students: int
    total_points_distributed: int
    total_points_exchanged: int
    top_students: List[PointRankingResponse]
