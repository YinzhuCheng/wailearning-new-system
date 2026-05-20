"""Static guardrail for CourseEval schema-repair governance.

The repository currently has no Alembic tree. Compatibility DDL lives in
bootstrap.ensure_schema_updates(), so schema-sensitive changes need an explicit
audit path. This script checks that the high-risk schema governance anchors stay
present and aligned with the current model conventions.
"""

from __future__ import annotations

import argparse
from pathlib import Path


REQUIRED_BOOTSTRAP_TOKENS = {
    "ensure_schema_updates": "schema repair entrypoint must exist",
    "Base.metadata.create_all(bind=engine)": "startup must keep create_all in the bootstrap path",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS student_id": "canonical student account binding DDL",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_student_id_unique": "student account binding uniqueness guard",
    "CREATE TABLE IF NOT EXISTS subject_class_links": "required-course multi-class binding table",
    "CREATE TABLE IF NOT EXISTS learning_notes": "learning notes table repair",
    "CREATE TABLE IF NOT EXISTS learning_note_resources": "learning-note resources table repair",
    "CREATE TABLE IF NOT EXISTS course_discussion_entries": "course discussion table repair",
    "ALTER TABLE course_materials ADD COLUMN IF NOT EXISTS content_format": "course material content-format DDL",
    "ALTER TABLE homework_submissions ADD COLUMN IF NOT EXISTS content_format": "homework submission content-format DDL",
}

REQUIRED_MODEL_TOKENS = {
    "student_id = Column(Integer, ForeignKey(\"students.id\", use_alter=True), nullable=True, unique=True, index=True)": "User.student_id model binding",
    "__tablename__ = \"subject_class_links\"": "SubjectClassLink ORM table",
    "__tablename__ = \"learning_notes\"": "LearningNote ORM table",
    "__tablename__ = \"learning_note_resources\"": "LearningNoteResource ORM table",
    "__tablename__ = \"course_discussion_entries\"": "CourseDiscussionEntry ORM table",
    "content_format = Column(String, nullable=False, default=\"markdown\")": "content-format ORM fields",
}

REQUIRED_DOC_TOKENS = {
    "There is **no separate Alembic migration tree**": "data-model no-Alembic warning",
    "ensure_schema_updates": "schema repair docs must point at bootstrap.ensure_schema_updates",
    "users.student_id": "canonical student account binding docs",
}


def missing_tokens(text: str, required: dict[str, str], path: str) -> list[str]:
    return [
        f"{path}: missing {description}: {token}"
        for token, description in required.items()
        if token not in text
    ]


def check_schema_governance(repo_root: Path) -> list[str]:
    bootstrap_path = repo_root / "apps/backend/courseeval_backend/bootstrap.py"
    models_path = repo_root / "apps/backend/courseeval_backend/db/models.py"
    data_model_doc = repo_root / "docs/reference/DATA_MODEL_ESSENTIALS.md"
    issues: list[str] = []
    for path in (bootstrap_path, models_path, data_model_doc):
        if not path.exists():
            issues.append(f"{path.relative_to(repo_root).as_posix()}: missing required schema governance file")
    if issues:
        return issues
    bootstrap = bootstrap_path.read_text(encoding="utf-8")
    models = models_path.read_text(encoding="utf-8")
    doc = data_model_doc.read_text(encoding="utf-8")
    issues.extend(
        missing_tokens(
            bootstrap,
            REQUIRED_BOOTSTRAP_TOKENS,
            bootstrap_path.relative_to(repo_root).as_posix(),
        )
    )
    issues.extend(
        missing_tokens(
            models,
            REQUIRED_MODEL_TOKENS,
            models_path.relative_to(repo_root).as_posix(),
        )
    )
    issues.extend(
        missing_tokens(
            doc,
            REQUIRED_DOC_TOKENS,
            data_model_doc.relative_to(repo_root).as_posix(),
        )
    )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    issues = check_schema_governance(repo_root)
    if issues:
        print("Schema governance check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("Schema governance check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
