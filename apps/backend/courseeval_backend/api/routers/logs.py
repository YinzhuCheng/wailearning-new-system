from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from datetime import datetime
from apps.backend.courseeval_backend.core.auth import get_current_active_user
from apps.backend.courseeval_backend.db.database import get_db
from apps.backend.courseeval_backend.db.models import OperationLog, User, UserRole
from apps.backend.courseeval_backend.api.schemas import OperationLogResponse, OperationLogListResponse

router = APIRouter(prefix="/api/logs", tags=["操作日志"])


def _ensure_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only administrators can access logs.")

@router.get("", response_model=OperationLogListResponse)
def get_logs(
    user_id: Optional[int] = Query(None, description="用户ID"),
    action: Optional[str] = Query(None, description="操作类型（登录、创建、修改、删除、导出）"),
    target_type: Optional[str] = Query(None, description="操作对象类型（学生、成绩、考勤、用户等）"),
    start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_admin(current_user)
    query = db.query(OperationLog)

    if user_id:
        query = query.filter(OperationLog.user_id == user_id)

    if action:
        query = query.filter(OperationLog.action == action)

    if target_type:
        query = query.filter(OperationLog.target_type == target_type)

    if start_date:
        try:
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(OperationLog.created_at >= start_datetime)
        except ValueError:
            pass

    if end_date:
        try:
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
            query = query.filter(OperationLog.created_at <= end_datetime)
        except ValueError:
            pass

    total = query.count()
    logs = query.order_by(desc(OperationLog.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    return OperationLogListResponse(total=total, data=logs)

@router.get("/{log_id}", response_model=OperationLogResponse)
def get_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_admin(current_user)
    log = db.query(OperationLog).filter(OperationLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="日志不存在")
    return log

@router.get("/stats/summary")
def get_log_stats(
    start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_admin(current_user)
    query = db.query(OperationLog)

    if start_date:
        try:
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(OperationLog.created_at >= start_datetime)
        except ValueError:
            pass

    if end_date:
        try:
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
            query = query.filter(OperationLog.created_at <= end_datetime)
        except ValueError:
            pass

    total_logs = query.count()

    from sqlalchemy import func
    stats_start_datetime = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if start_date:
        try:
            stats_start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            pass

    action_stats = db.query(
        OperationLog.action,
        func.count(OperationLog.id)
    ).filter(
        OperationLog.created_at >= stats_start_datetime
    ).group_by(OperationLog.action).all()

    target_stats = db.query(
        OperationLog.target_type,
        func.count(OperationLog.id)
    ).filter(
        OperationLog.created_at >= stats_start_datetime
    ).group_by(OperationLog.target_type).all()

    return {
        "total": total_logs,
        "today": db.query(OperationLog).filter(
            OperationLog.created_at >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        ).count(),
        "action_stats": [{"action": a, "count": c} for a, c in action_stats],
        "target_stats": [{"type": t, "count": c} for t, c in target_stats]
    }
