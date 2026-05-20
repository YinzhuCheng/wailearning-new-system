# 旧系统到新系统迁移说明

本仓库是新系统发布副本。旧系统来源建议使用 `YinzhuCheng/wailearning-old-system`。

## 迁移前准备

- 准备旧系统数据库备份文件，例如 `old-system.dump`。
- 准备旧系统附件压缩包，例如 `old-uploads.tar.gz`。
- 在新系统服务器完成部署，并确认 `.env.production` 中的数据库、密钥、域名和 LLM 参数已经替换。
- 确认新系统 PostgreSQL 版本、字符集和时区配置符合生产要求。

## 数据导入步骤

1. 停止新系统后端服务：`systemctl stop <NEW_BACKEND_SERVICE>`。
2. 创建或清空新系统数据库，保留一次恢复前快照。
3. 恢复旧系统数据：`pg_restore --clean --if-exists --dbname "$DATABASE_URL" old-system.dump`。
4. 解压附件：`tar -xzf old-uploads.tar.gz -C <NEW_UPLOAD_PARENT_DIR>`。
5. 检查上传目录权限，确保运行后端服务的用户可以读写。
6. 启动新系统后端服务：`systemctl start <NEW_BACKEND_SERVICE>`。
7. 登录管理员、教师、学生、家长入口做 smoke test。

## 迁移后核对清单

- 管理员可以登录并看到班级、用户、学生和课程数据。
- 教师可以查看课程、作业、成绩、通知和资料。
- 学生可以进入课程、提交作业、查看通知和成绩。
- 家长入口可以用家长码访问学生信息。
- 附件上传、下载、预览路径正常。
- LLM 作业批改配置可见；如果启用 LLM，确认 API key、base URL、模型名和配额策略已经替换为生产值。

## 回滚策略

- 新系统验证完成前不要删除旧系统数据库和附件。
- 域名切换失败时，把 DNS A 记录或 Nginx upstream 切回旧系统公网 IP。
- 回滚后重新冻结旧系统写入，再重新导出迁移包。
