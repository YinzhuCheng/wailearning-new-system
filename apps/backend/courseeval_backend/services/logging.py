from sqlalchemy.orm import Session
from apps.backend.courseeval_backend.db.models import OperationLog
from typing import Optional

class LogService:
    @staticmethod
    def log(
        db: Session,
        action: str,
        target_type: str,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        target_id: Optional[int] = None,
        target_name: Optional[str] = None,
        details: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        result: str = "success"
    ):
        log_entry = OperationLog(
            user_id=user_id,
            username=username,
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            result=result
        )
        db.add(log_entry)
        db.commit()

    @staticmethod
    def log_login(db: Session, user_id: int, username: str, ip_address: str = None, user_agent: str = None, success: bool = True):
        LogService.log(
            db=db,
            action="登录",
            target_type="认证",
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            details=f"用户 {username} {'登录成功' if success else '登录失败'}",
            result="success" if success else "failed"
        )

    @staticmethod
    def log_create(db: Session, user_id: int, username: str, target_type: str, target_id: int, target_name: str, ip_address: str = None, user_agent: str = None):
        LogService.log(
            db=db,
            action="创建",
            target_type=target_type,
            user_id=user_id,
            username=username,
            target_id=target_id,
            target_name=target_name,
            details=f"创建 {target_type}：{target_name}",
            ip_address=ip_address,
            user_agent=user_agent
        )

    @staticmethod
    def log_update(db: Session, user_id: int, username: str, target_type: str, target_id: int, target_name: str, changes: str = None, ip_address: str = None, user_agent: str = None):
        details = f"修改 {target_type}：{target_name}"
        if changes:
            details += f"，变更：{changes}"
        LogService.log(
            db=db,
            action="修改",
            target_type=target_type,
            user_id=user_id,
            username=username,
            target_id=target_id,
            target_name=target_name,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent
        )

    @staticmethod
    def log_delete(db: Session, user_id: int, username: str, target_type: str, target_id: int, target_name: str, ip_address: str = None, user_agent: str = None):
        LogService.log(
            db=db,
            action="删除",
            target_type=target_type,
            user_id=user_id,
            username=username,
            target_id=target_id,
            target_name=target_name,
            details=f"删除 {target_type}：{target_name}",
            ip_address=ip_address,
            user_agent=user_agent
        )

    @staticmethod
    def log_export(db: Session, user_id: int, username: str, target_type: str, target_name: str, ip_address: str = None, user_agent: str = None):
        LogService.log(
            db=db,
            action="导出",
            target_type=target_type,
            user_id=user_id,
            username=username,
            target_name=target_name,
            details=f"导出 {target_type}：{target_name}",
            ip_address=ip_address,
            user_agent=user_agent
        )
