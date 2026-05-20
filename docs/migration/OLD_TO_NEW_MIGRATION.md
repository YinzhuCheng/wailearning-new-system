# 旧系统到新系统迁移说明

本仓库是新系统发布副本。旧系统来源建议使用 `YinzhuCheng/wailearning-old-system`。

## 推荐方式

优先使用短启动器导入迁移包，避免在 Workbench 里手写多行 `pg_restore`、`tar`、`systemctl` 命令时出现换行、缩进或参数截断问题。

1. 在旧系统服务器执行旧系统仓库的 `docs/migration/ALIYUN_WORKBENCH_EXPORT_MIGRATION_BUNDLE.txt`。
2. 将生成的 `/root/wailearning-migration/<label>.tar.gz` 复制到新系统服务器。
3. 在新系统服务器执行 `docs/migration/ALIYUN_WORKBENCH_IMPORT_MIGRATION_BUNDLE.txt`。
4. 导入脚本会先备份新系统数据库，再停止后端、恢复旧数据、恢复附件、运行 bootstrap、重启服务并做健康检查。

## 迁移前准备

- 准备旧系统迁移包，例如 `/root/old-to-new-20260520230000.tar.gz`。
- 在新系统服务器完成部署，并确认 `.env.production` 中的数据库、密钥、域名和 LLM 参数已经替换。
- 确认新系统后端健康：`curl -fsS http://127.0.0.1:8002/api/health`。
- 导入会覆盖新系统数据库；启动器要求显式设置 `CONFIRM_IMPORT="YES"`。

## 手动导入参考

如果不使用启动器，手动导入至少包含以下步骤：

```bash
systemctl stop wailearning-new-system.service
pg_dump -Fc "$DATABASE_URL" -f before-import.dump
pg_restore --clean --if-exists --no-owner --dbname "$DATABASE_URL" old-system.dump
tar -xzf old-uploads.tar.gz -C <NEW_UPLOAD_PARENT_DIR>
/opt/wailearning-new-system/current/.venv/bin/python -m apps.backend.courseeval_backend.bootstrap
systemctl start wailearning-new-system.service
curl -fsS http://127.0.0.1:8002/api/health
```

手动方式容易遗漏导入前备份、附件路径和 bootstrap，生产迁移建议使用启动器。

## 迁移后核对清单

- 管理员可以登录并看到班级、用户、学生和课程数据。
- 教师可以查看课程、作业、成绩、通知和资料。
- 学生可以进入课程、提交作业、查看通知和成绩。
- 家长入口可以用家长码访问学生信息。
- 附件上传、下载、预览路径正常。
- LLM 作业批改配置可见；如果启用 LLM，确认 API key、base URL、模型名和配额策略已经替换为生产值。

## 回滚策略

- 新系统验证完成前不要删除旧系统数据库和附件。
- 导入脚本会创建导入前数据库备份，默认位置是 `/root/wailearning-migration-import-backups/`。
- 域名切换失败时，把 DNS A 记录或 Nginx upstream 切回旧系统公网 IP。
- 回滚后重新冻结旧系统写入，再重新导出迁移包。
