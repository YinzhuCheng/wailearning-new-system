from datetime import datetime
from enum import Enum
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.backend.courseeval_backend.api.schema_defs.appearance import (
    AppearancePresetResponse,
    AppearanceStyleConfig,
    UserAppearanceStateResponse,
    UserAppearanceStyleCreate,
    UserAppearanceStyleResponse,
    UserAppearanceStyleUpdate,
)
from apps.backend.courseeval_backend.api.schema_defs.attendance import (
    AttendanceCreate,
    AttendanceListResponse,
    AttendanceResponse,
    AttendanceStatus,
    AttendanceUpdate,
)
from apps.backend.courseeval_backend.api.schema_defs.dashboard import ClassRanking, DashboardStats, StudentRanking
from apps.backend.courseeval_backend.api.schema_defs.files import AttachmentUploadResponse
from apps.backend.courseeval_backend.api.schema_defs.notifications import (
    NotificationBase,
    NotificationCreate,
    NotificationListResponse,
    NotificationResponse,
    NotificationSyncStatus,
    NotificationUpdate,
)
from apps.backend.courseeval_backend.api.schema_defs.operations import (
    OperationLogListResponse,
    OperationLogResponse,
    SystemSettingResponse,
    SystemSettingsResponse,
    SystemSettingUpdate,
)
from apps.backend.courseeval_backend.api.schema_defs.points import (
    PointAddRequest,
    PointExchangeListResponse,
    PointExchangeRequest,
    PointExchangeResponse,
    PointItemCreate,
    PointItemResponse,
    PointItemUpdate,
    PointRankingResponse,
    PointRecordListResponse,
    PointRecordResponse,
    PointRuleCreate,
    PointRuleResponse,
    PointRuleUpdate,
    PointStatsResponse,
    StudentPointResponse,
)
from apps.backend.courseeval_backend.api.schema_defs.roster import (
    CourseEnrollmentResponse,
    CourseEnrollmentTypeUpdate,
    CourseRosterStudentInput,
)

ContentFormatLiteral = Literal["markdown", "plain"]
class UserRole(str, Enum):
    ADMIN = "admin"
    CLASS_TEACHER = "class_teacher"
    TEACHER = "teacher"
    STUDENT = "student"


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"


class UserBase(BaseModel):
    username: str
    real_name: str
    role: str = UserRole.TEACHER.value
    class_id: Optional[int] = None
    student_id: Optional[int] = None

    @field_validator("role", mode="before")
    @classmethod
    def convert_role(cls, value):
        if isinstance(value, UserRole):
            return value.value
        return value


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    username: Optional[str] = None
    real_name: Optional[str] = None
    role: Optional[str] = None
    class_id: Optional[int] = None
    student_id: Optional[int] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    class_id: Optional[int] = None
    avatar_url: Optional[str] = None
    discussion_page_size: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class ProfileSelfUpdate(BaseModel):
    real_name: Optional[str] = Field(None, max_length=120)
    discussion_page_size: Optional[int] = Field(
        default=None,
        ge=5,
        le=50,
        description="Replies per page in homework/material discussions; omit to leave unchanged; null clears to default 5.",
    )

    @field_validator("real_name")
    @classmethod
    def strip_real_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("real_name cannot be empty.")
        return stripped

    @model_validator(mode="after")
    def require_at_least_one_field(self):
        if self.real_name is None and self.discussion_page_size is None:
            raise ValueError("Provide real_name and/or discussion_page_size.")
        return self


class DiscussionLinkedTargetInput(BaseModel):
    target_type: Literal["homework", "material", "learning_note", "course", "discussion_entry"]
    target_id: int = Field(..., ge=1)


class DiscussionLinkedTargetResponse(BaseModel):
    target_type: Literal["homework", "material", "learning_note", "course", "discussion_entry"]
    target_id: int
    target_label: str
    title: str
    subject_id: Optional[int] = None
    subject_name: Optional[str] = None
    class_id: Optional[int] = None
    class_name: Optional[str] = None
    secondary_text: Optional[str] = None
    available: bool = True
    meta: Optional[dict[str, Any]] = None


class RecentPostAuthorResponse(BaseModel):
    id: int
    username: str
    real_name: Optional[str] = None
    role: str
    avatar_url: Optional[str] = None
    class_id: Optional[int] = None
    class_name: Optional[str] = None


class RecentPostItemResponse(BaseModel):
    id: str
    kind: Literal["comment", "note", "material", "homework", "course"]
    source_type: Literal[
        "course_discussion_entry",
        "learning_note_discussion_entry",
        "learning_note",
        "course_material",
        "homework",
        "course",
    ]
    object_id: int
    target_id: Optional[int] = None
    title: str
    body_preview: Optional[str] = None
    body_format: Optional[ContentFormatLiteral] = None
    created_at: datetime
    subject_id: Optional[int] = None
    subject_name: Optional[str] = None
    class_id: Optional[int] = None
    class_name: Optional[str] = None
    context_title: Optional[str] = None
    target: DiscussionLinkedTargetResponse
    has_attachment: bool = False


class RecentPostGroupResponse(BaseModel):
    kind: Literal["comment", "note", "material", "homework", "course"]
    label: str
    total: int
    latest_created_at: Optional[datetime] = None
    data: List[RecentPostItemResponse]


class RecentPostsResponse(BaseModel):
    author: RecentPostAuthorResponse
    page: int
    page_size: int
    total: int
    data: List[RecentPostItemResponse]


class RecentPostsGroupedResponse(BaseModel):
    author: RecentPostAuthorResponse
    group_limit: int
    groups: List[RecentPostGroupResponse]


class CourseDiscussionEntryResponse(BaseModel):
    id: int
    target_type: str
    target_id: int
    subject_id: int
    class_id: int
    author_user_id: int
    author_student_id: Optional[int] = None
    author_real_name: str
    author_username: str
    author_role: str
    author_avatar_url: Optional[str] = None
    body: str
    body_format: ContentFormatLiteral = "markdown"
    linked_targets: List["DiscussionLinkedTargetResponse"] = Field(default_factory=list)
    message_kind: str = "human"
    llm_invocation: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CourseDiscussionListResponse(BaseModel):
    page: int
    page_size: int
    total: int
    data: List[CourseDiscussionEntryResponse]


class CourseDiscussionCreate(BaseModel):
    target_type: Literal["homework", "material"]
    target_id: int = Field(..., ge=1)
    subject_id: int = Field(..., ge=1)
    class_id: int = Field(..., ge=1)
    body: str = Field(..., min_length=1, max_length=8000)
    body_format: ContentFormatLiteral = "markdown"
    linked_targets: List["DiscussionLinkedTargetInput"] = Field(default_factory=list)
    invoke_llm: bool = False

    @field_validator("body_format", mode="before")
    @classmethod
    def normalize_body_format(cls, value):
        from apps.backend.courseeval_backend.domains.text_content_format import normalize_content_format

        return normalize_content_format(value if isinstance(value, str) else None)


class LearningNoteVisibility(str, Enum):
    PRIVATE = "private"
    COURSE = "course"


class LearningNoteResourceResponse(BaseModel):
    id: int
    note_id: int
    chapter_id: Optional[int] = None
    title: str
    content: Optional[str] = None
    content_format: ContentFormatLiteral = "markdown"
    attachment_name: Optional[str] = None
    attachment_url: Optional[str] = None
    source_material_id: Optional[int] = None
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LearningNoteChapterNode(BaseModel):
    id: int
    note_id: int
    parent_id: Optional[int] = None
    title: str
    sort_order: int
    source_chapter_id: Optional[int] = None
    resources: List[LearningNoteResourceResponse] = Field(default_factory=list)
    children: List["LearningNoteChapterNode"] = Field(default_factory=list)


class LearningNoteBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    description: Optional[str] = Field(None, max_length=4000)
    subject_id: Optional[int] = Field(None, ge=1)
    visibility: LearningNoteVisibility = LearningNoteVisibility.PRIVATE

    @field_validator("title")
    @classmethod
    def strip_learning_note_title(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("title cannot be empty.")
        return stripped

    @field_validator("description")
    @classmethod
    def strip_learning_note_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class LearningNoteCreate(LearningNoteBase):
    copy_from_subject_id: Optional[int] = Field(None, ge=1)
    copy_chapters: bool = False
    copy_materials: bool = False


class LearningNoteUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=160)
    description: Optional[str] = Field(None, max_length=4000)
    subject_id: Optional[int] = Field(None, ge=1)
    visibility: Optional[LearningNoteVisibility] = None

    @field_validator("title")
    @classmethod
    def strip_learning_note_update_title(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("title cannot be empty.")
        return stripped

    @field_validator("description")
    @classmethod
    def strip_learning_note_update_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class LearningNoteResponse(LearningNoteBase):
    id: int
    owner_user_id: int
    owner_real_name: Optional[str] = None
    owner_username: Optional[str] = None
    owner_role: Optional[str] = None
    subject_name: Optional[str] = None
    source_subject_id: Optional[int] = None
    source_subject_name: Optional[str] = None
    copied_materials: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LearningNoteListResponse(BaseModel):
    total: int
    data: List[LearningNoteResponse]


class LearningNoteDetailResponse(LearningNoteResponse):
    chapters: List[LearningNoteChapterNode] = Field(default_factory=list)
    loose_resources: List[LearningNoteResourceResponse] = Field(default_factory=list)


class LearningNoteChapterCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None


class LearningNoteChapterUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=160)
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None


class LearningNoteResourceCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: Optional[str] = None
    content_format: ContentFormatLiteral = "markdown"
    attachment_name: Optional[str] = None
    attachment_url: Optional[str] = None
    chapter_id: Optional[int] = None
    sort_order: Optional[int] = None

    @field_validator("content_format", mode="before")
    @classmethod
    def validate_note_resource_content_format(cls, value):
        from apps.backend.courseeval_backend.domains.text_content_format import normalize_content_format

        return normalize_content_format(value if isinstance(value, str) else None)


class LearningNoteResourceUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = None
    content_format: Optional[ContentFormatLiteral] = None
    attachment_name: Optional[str] = None
    attachment_url: Optional[str] = None
    chapter_id: Optional[int] = None
    sort_order: Optional[int] = None

    @field_validator("content_format", mode="before")
    @classmethod
    def validate_note_resource_update_content_format(cls, value):
        if value is None:
            return None
        from apps.backend.courseeval_backend.domains.text_content_format import normalize_content_format

        return normalize_content_format(value if isinstance(value, str) else None)


class LearningNoteDiscussionEntryResponse(BaseModel):
    id: int
    note_id: int
    author_user_id: int
    author_student_id: Optional[int] = None
    author_real_name: Optional[str] = None
    author_username: str
    author_role: str
    author_avatar_url: Optional[str] = None
    body: str
    body_format: ContentFormatLiteral = "markdown"
    linked_targets: List["DiscussionLinkedTargetResponse"] = Field(default_factory=list)
    message_kind: str = "human"
    llm_invocation: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LearningNoteDiscussionListResponse(BaseModel):
    page: int
    page_size: int
    total: int
    data: List[LearningNoteDiscussionEntryResponse]


class LearningNoteDiscussionCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=8000)
    body_format: ContentFormatLiteral = "markdown"
    linked_targets: List["DiscussionLinkedTargetInput"] = Field(default_factory=list)
    invoke_llm: bool = False

    @field_validator("body_format", mode="before")
    @classmethod
    def normalize_note_discussion_body_format(cls, value):
        from apps.backend.courseeval_backend.domains.text_content_format import normalize_content_format

        return normalize_content_format(value if isinstance(value, str) else None)


class DiscussionLinkTargetSearchResponse(BaseModel):
    data: List[DiscussionLinkedTargetResponse]


class StudentRosterUpsertFromUsersRequest(BaseModel):
    user_ids: List[int]


class StudentRosterUpsertFromUsersError(BaseModel):
    user_id: Optional[int] = None
    username: Optional[str] = None
    reason: str


class StudentRosterUpsertFromUsersResponse(BaseModel):
    total: int
    created: int
    updated: int
    skipped: int
    errors: List[StudentRosterUpsertFromUsersError]


class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class MessageResponse(BaseModel):
    message: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        encoded = value.encode("utf-8")
        if len(encoded) < 8:
            raise ValueError("New password must be at least 8 characters.")
        if len(encoded) > 72:
            raise ValueError("New password must be 72 bytes or fewer.")
        return value

    @model_validator(mode="after")
    def validate_password_confirmation(self):
        if self.new_password != self.confirm_password:
            raise ValueError("Password confirmation does not match.")
        if self.current_password == self.new_password:
            raise ValueError("New password must be different from current password.")
        return self


class ForgotPasswordRequest(BaseModel):
    """Non-admin users submit from the login page; server notifies administrators."""

    username: str = Field(..., min_length=1, max_length=120)


class AdminResetUserPasswordRequest(BaseModel):
    """Admin reset: optional explicit password; required when target is another admin."""

    new_password: Optional[str] = Field(default=None, max_length=128)


class ClassCreate(BaseModel):
    name: str
    grade: int


class ClassUpdate(BaseModel):
    name: Optional[str] = None
    grade: Optional[int] = None


class ClassResponse(BaseModel):
    id: int
    name: str
    grade: int
    created_at: datetime
    student_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class StudentBase(BaseModel):
    name: str
    student_no: Optional[str] = None
    gender: Gender
    phone: Optional[str] = None
    parent_phone: Optional[str] = None
    address: Optional[str] = None
    class_id: Optional[int] = None


class StudentCreate(StudentBase):
    gender: Gender = Gender.MALE


class StudentUpdate(BaseModel):
    name: Optional[str] = None
    student_no: Optional[str] = None
    gender: Optional[Gender] = None
    phone: Optional[str] = None
    parent_phone: Optional[str] = None
    address: Optional[str] = None
    class_id: Optional[int] = None


class StudentResponse(BaseModel):
    """
    Roster row exposed by read/list APIs.

    Serializers still expose ``class_id`` as optional for legacy-database
    compatibility, but normal create/update/repair flows backfill missing
    student classes into the reserved temporary class instead of keeping active
    students unassigned.
    """

    id: int
    name: str
    student_no: str
    gender: Gender = Gender.MALE
    phone: Optional[str] = None
    parent_phone: Optional[str] = None
    address: Optional[str] = None
    class_id: Optional[int] = None
    teacher_id: Optional[int] = None
    created_at: datetime
    class_name: Optional[str] = None
    parent_code: Optional[str] = None
    has_user: bool = False
    bound_user_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class StudentListResponse(BaseModel):
    total: int
    data: List[StudentResponse]


class CourseTimeItem(BaseModel):
    weekly_schedule: str
    course_start_at: datetime
    course_end_at: datetime

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.course_end_at < self.course_start_at:
            raise ValueError("Course end time must be later than start time.")
        return self


class SubjectClassLinkInput(BaseModel):
    class_id: int = Field(..., ge=1)
    enrollment_mode: Literal["all_in_class", "roster_subset"] = "all_in_class"


class SubjectClassLinkResponse(BaseModel):
    class_id: int
    class_name: Optional[str] = None
    enrollment_mode: str = "all_in_class"


class SubjectCreate(BaseModel):
    name: str
    teacher_id: Optional[int] = None
    class_id: Optional[int] = None
    class_links: Optional[List[SubjectClassLinkInput]] = None
    class_name: Optional[str] = None
    semester_id: Optional[int] = None
    course_type: str = "required"
    status: str = "active"
    semester: Optional[str] = None
    course_times: Optional[List[CourseTimeItem]] = None
    description: Optional[str] = None
    students: Optional[List["CourseRosterStudentInput"]] = None


class SubjectUpdate(BaseModel):
    name: Optional[str] = None
    teacher_id: Optional[int] = None
    class_id: Optional[int] = None
    class_links: Optional[List[SubjectClassLinkInput]] = None
    semester_id: Optional[int] = None
    course_type: Optional[str] = None
    status: Optional[str] = None
    semester: Optional[str] = None
    course_times: Optional[List[CourseTimeItem]] = None
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    remove_cover_image: bool = False


class SubjectResponse(BaseModel):
    id: int
    name: str
    teacher_id: Optional[int] = None
    class_id: Optional[int] = None
    semester_id: Optional[int] = None
    course_type: str = "required"
    status: str = "active"
    semester: Optional[str] = None
    course_times: List[CourseTimeItem] = Field(default_factory=list)
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    teacher_name: Optional[str] = None
    class_name: Optional[str] = None
    class_links: List[SubjectClassLinkResponse] = Field(default_factory=list)
    student_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StudentCourseCatalogItem(SubjectResponse):
    """Student-facing schoolwide course list with enrollment hints (read-only browse + elective self-enroll)."""

    is_enrolled: bool = False
    enrollment_hint: str = ""
    can_self_enroll_elective: bool = False


class SubjectRosterEnrollRequest(BaseModel):
    """Add enrollments only for students already on the course class roster (same class_id)."""

    student_ids: List[int] = Field(default_factory=list)


class SubjectRosterEnrollResult(BaseModel):
    created: int = 0
    skipped_already_enrolled: int = 0
    skipped_not_in_class_roster: int = 0
    skipped_not_found: int = 0


class StudentElectiveSelfEnrollResult(BaseModel):
    """Student voluntarily joined an elective course."""

    subject_id: int
    created: bool = False
    already_enrolled: bool = False


class StudentElectiveSelfDropResult(BaseModel):
    subject_id: int
    removed: bool = False


class StudentLLMCourseQuotaRow(BaseModel):
    subject_id: int
    subject_name: str
    usage_date: str
    quota_timezone: str
    daily_student_token_limit: Optional[int] = None
    student_used_tokens_today: Optional[int] = None
    student_remaining_tokens_today: Optional[int] = None
    course_used_tokens_today: Optional[int] = None
    course_usage_ratio: Optional[float] = None


class StudentLLMQuotasSummaryResponse(BaseModel):
    """System-wide LLM token budget for the logged-in student.

    `courses` rows may still carry per-course usage fields for diagnostics, but the effective
    cap and remaining balance are the top-level student totals (one pool per student per day).
    """

    courses: list[StudentLLMCourseQuotaRow] = Field(default_factory=list)
    global_default_daily_student_tokens: Optional[int] = None
    usage_date: Optional[str] = None
    quota_timezone: Optional[str] = None
    daily_student_token_limit: Optional[int] = None
    student_used_tokens_today: Optional[int] = None
    student_remaining_tokens_today: Optional[int] = None
    uses_personal_override: bool = False


class StudentLLMQuotaUsageResponse(BaseModel):
    subject_id: int
    usage_date: str
    quota_timezone: str
    """Effective per-student daily cap in the system-wide LLM usage pool."""
    daily_student_token_limit: Optional[int] = None
    global_default_daily_student_tokens: Optional[int] = None
    uses_personal_override: bool = False
    student_used_tokens_today: Optional[int] = None
    student_remaining_tokens_today: Optional[int] = None
    course_used_tokens_today: Optional[int] = None
    course_usage_ratio: Optional[float] = None


class LLMGlobalQuotaPolicyResponse(BaseModel):
    id: int
    default_daily_student_tokens: int
    quota_timezone: str
    estimated_chars_per_token: float = 4.0
    estimated_image_tokens: int = 850
    max_parallel_grading_tasks: int = 3


class LLMGlobalQuotaPolicyUpdate(BaseModel):
    default_daily_student_tokens: Optional[int] = Field(default=None, ge=1)
    quota_timezone: Optional[str] = None
    estimated_chars_per_token: Optional[float] = Field(default=None, gt=0)
    estimated_image_tokens: Optional[int] = Field(default=None, ge=1)
    max_parallel_grading_tasks: Optional[int] = Field(default=None, ge=1, le=64)


class LLMQuotaBulkOverrideRequest(BaseModel):
    """Apply the same per-student daily cap to everyone in scope (or clear overrides)."""

    scope: str = Field(..., description="one of: all, class, subject")
    class_id: Optional[int] = None
    subject_id: Optional[int] = None
    daily_tokens: Optional[int] = Field(default=None, ge=1)
    clear_override: bool = False

    @model_validator(mode="after")
    def _validate_scope(self) -> "LLMQuotaBulkOverrideRequest":
        s = (self.scope or "").strip().lower()
        if s not in {"all", "class", "subject"}:
            raise ValueError("scope must be all, class, or subject")
        object.__setattr__(self, "scope", s)
        if s == "class" and not self.class_id:
            raise ValueError("class_id is required when scope is class")
        if s == "subject" and not self.subject_id:
            raise ValueError("subject_id is required when scope is subject")
        if not self.clear_override and self.daily_tokens is None:
            raise ValueError("daily_tokens is required unless clear_override is true")
        if self.clear_override and self.daily_tokens is not None:
            raise ValueError("clear_override cannot be combined with daily_tokens")
        return self


class LLMQuotaBulkOverrideResponse(BaseModel):
    affected_students: int
    default_daily_student_tokens: Optional[int] = None


class LLMStudentQuotaOverrideUpsert(BaseModel):
    daily_tokens: Optional[int] = Field(default=None, ge=1)
    clear_override: bool = False

    @model_validator(mode="after")
    def _xor(self) -> "LLMStudentQuotaOverrideUpsert":
        if self.clear_override and self.daily_tokens is not None:
            raise ValueError("clear_override cannot be combined with daily_tokens")
        if not self.clear_override and self.daily_tokens is None:
            raise ValueError("Provide daily_tokens or set clear_override to true")
        return self


class UserBatchSetClassRequest(BaseModel):
    user_ids: List[int] = Field(default_factory=list)
    class_id: int


class UserBatchSetClassError(BaseModel):
    user_id: int
    reason: str


class UserBatchSetClassResponse(BaseModel):
    updated: int = 0
    errors: List[UserBatchSetClassError] = Field(default_factory=list)


CourseRosterStudentInput.model_rebuild(_types_namespace={"Gender": Gender})
SubjectCreate.model_rebuild()


class SemesterCreate(BaseModel):
    name: str
    year: int
    is_current: bool = False


class SemesterUpdate(BaseModel):
    name: Optional[str] = None
    year: Optional[int] = None
    is_current: Optional[bool] = None


class SemesterResponse(BaseModel):
    id: int
    name: str
    year: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScoreBase(BaseModel):
    student_id: int
    subject_id: int
    class_id: int
    semester: str
    exam_type: str
    score: float
    exam_date: Optional[str] = None


class ScoreCreate(ScoreBase):
    pass


class ScoreUpdate(BaseModel):
    score: Optional[float] = None
    exam_type: Optional[str] = None
    exam_date: Optional[str] = None
    semester: Optional[str] = None


class ScoreResponse(ScoreBase):
    id: int
    student_name: Optional[str] = None
    subject_name: Optional[str] = None
    class_name: Optional[str] = None
    exam_date: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ScoreListResponse(BaseModel):
    total: int
    data: List[ScoreResponse]


class CourseExamWeightItem(BaseModel):
    exam_type: str
    weight: float


class CourseExamWeightResponse(CourseExamWeightItem):
    id: int
    subject_id: int

    model_config = ConfigDict(from_attributes=True)


class CourseExamWeightUpdateRequest(BaseModel):
    items: List[CourseExamWeightItem]


class CourseGradeSchemeResponse(BaseModel):
    subject_id: int
    homework_weight: float
    extra_daily_weight: float


class CourseGradeSchemeUpdate(BaseModel):
    homework_weight: float = Field(..., ge=0, le=100)
    extra_daily_weight: float = Field(..., ge=0, le=100)


class ScoreCompositionHomeworkItem(BaseModel):
    homework_id: int
    title: str
    max_score: float
    review_score: Optional[float] = None
    percent_equivalent: Optional[float] = None


class ScoreCompositionExamWeight(BaseModel):
    exam_type: str
    weight: float


class ScoreCompositionScheme(BaseModel):
    homework_weight: float
    extra_daily_weight: float
    other_daily_label: str
    exam_weights: List[ScoreCompositionExamWeight]
    inner_parts_sum: float
    inner_parts_valid: bool


class ScoreCompositionResponse(BaseModel):
    student_id: Optional[int] = None
    student_name: Optional[str] = None
    student_no: Optional[str] = None
    subject_id: int
    subject_name: str
    semester: str
    scheme: ScoreCompositionScheme
    homework_average_percent: Optional[float] = None
    homework_assignments: List[ScoreCompositionHomeworkItem] = Field(default_factory=list)
    other_daily_score: Optional[float] = None
    other_daily_score_id: Optional[int] = None
    exam_scores: dict[str, float] = Field(default_factory=dict)
    weighted_total: Optional[float] = None
    missing_for_total: List[str] = Field(default_factory=list)


class ScoreGradeAppealCreate(BaseModel):
    semester: str
    target_component: str = Field(..., min_length=1, max_length=64)
    reason_text: str = Field(..., min_length=1)
    homework_id: Optional[int] = None
    score_id: Optional[int] = None


class ScoreGradeAppealTeacherUpdate(BaseModel):
    teacher_response: str = Field(..., min_length=1)
    status: str = Field(default="resolved")


class ScoreGradeAppealResponse(BaseModel):
    id: int
    subject_id: int
    student_id: int
    student_name: Optional[str] = None
    homework_id: Optional[int] = None
    homework_title: Optional[str] = None
    score_id: Optional[int] = None
    semester: str
    target_component: str
    reason_text: str
    status: str
    teacher_response: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class HomeworkBase(BaseModel):
    title: str
    content: Optional[str] = None
    content_format: ContentFormatLiteral = "markdown"
    attachment_name: Optional[str] = None
    attachment_url: Optional[str] = None
    class_id: int
    subject_id: Optional[int] = None
    due_date: Optional[datetime] = None
    max_score: float = Field(default=100, gt=0)
    grade_precision: str = "integer"
    auto_grading_enabled: bool = False
    rubric_text: Optional[str] = None
    rubric_staff_only: Optional[str] = None
    reference_answer: Optional[str] = None
    response_language: Optional[str] = None
    allow_late_submission: bool = True
    late_submission_affects_score: bool = False
    max_submissions: Optional[int] = Field(
        default=None,
        description="Maximum submission attempts per student; null means unlimited.",
    )
    llm_routing_spec: Optional[dict[str, Any]] = Field(
        default=None,
        description="Per-homework LLM routing override: mode limit_to_preset_ids or latest_passing_validated.",
    )

    @field_validator("max_submissions")
    @classmethod
    def validate_max_submissions(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        if int(value) < 1:
            raise ValueError("max_submissions must be at least 1 when set.")
        if int(value) > 200:
            raise ValueError("max_submissions cannot exceed 200.")
        return int(value)

    @field_validator("grade_precision")
    @classmethod
    def validate_grade_precision(cls, value: str) -> str:
        normalized = (value or "integer").strip()
        if normalized not in {"integer", "decimal_1"}:
            raise ValueError("grade_precision must be integer or decimal_1.")
        return normalized

    @field_validator("content_format", mode="before")
    @classmethod
    def validate_homework_content_format(cls, value):
        from apps.backend.courseeval_backend.domains.text_content_format import normalize_content_format

        return normalize_content_format(value if isinstance(value, str) else None)


class HomeworkCreate(HomeworkBase):
    pass


class HomeworkUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    content_format: Optional[ContentFormatLiteral] = None
    attachment_name: Optional[str] = None
    attachment_url: Optional[str] = None
    remove_attachment: bool = False
    subject_id: Optional[int] = None
    due_date: Optional[datetime] = None
    max_score: Optional[float] = Field(default=None, gt=0)
    grade_precision: Optional[str] = None
    auto_grading_enabled: Optional[bool] = None
    rubric_text: Optional[str] = None
    rubric_staff_only: Optional[str] = None
    reference_answer: Optional[str] = None
    response_language: Optional[str] = None
    allow_late_submission: Optional[bool] = None
    late_submission_affects_score: Optional[bool] = None
    max_submissions: Optional[int] = None
    llm_routing_spec: Optional[dict[str, Any]] = None

    @field_validator("max_submissions")
    @classmethod
    def validate_max_submissions_update(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        if int(value) < 1:
            raise ValueError("max_submissions must be at least 1 when set.")
        if int(value) > 200:
            raise ValueError("max_submissions cannot exceed 200.")
        return int(value)

    @field_validator("grade_precision")
    @classmethod
    def validate_optional_grade_precision(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip()
        if normalized not in {"integer", "decimal_1"}:
            raise ValueError("grade_precision must be integer or decimal_1.")
        return normalized

    @field_validator("content_format", mode="before")
    @classmethod
    def validate_homework_update_content_format(cls, value):
        if value is None:
            return None
        from apps.backend.courseeval_backend.domains.text_content_format import normalize_content_format

        return normalize_content_format(value if isinstance(value, str) else None)


class HomeworkResponse(HomeworkBase):
    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime
    class_name: Optional[str] = None
    subject_name: Optional[str] = None
    creator_name: Optional[str] = None
    review_score: Optional[float] = None
    review_comment: Optional[str] = None
    used_llm_assist: Optional[bool] = None
    task_status: Optional[str] = None
    task_error: Optional[str] = None
    attempt_count: int = 0
    submissions_remaining: Optional[int] = None
    latest_submission_is_late: Optional[bool] = None
    grading_rule_hint: Optional[str] = None
    llm_routing_spec: Optional[dict[str, Any]] = None
    discussion_requires_context: bool = False

    model_config = ConfigDict(from_attributes=True)


class HomeworkBatchLateSubmissionUpdate(BaseModel):
    """批量更新多份作业的迟交策略（用于截止后统一允许补交等场景）。"""

    homework_ids: list[int] = Field(default_factory=list, min_length=1)
    allow_late_submission: Optional[bool] = None
    late_submission_affects_score: Optional[bool] = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "HomeworkBatchLateSubmissionUpdate":
        if self.allow_late_submission is None and self.late_submission_affects_score is None:
            raise ValueError("至少需要设置 allow_late_submission 或 late_submission_affects_score 之一。")
        return self


class HomeworkBatchRegradeRequest(BaseModel):
    """对某作业下多条学生提交批量入队 LLM 重评（仅 latest attempt）。"""

    submission_ids: Optional[list[int]] = None
    only_latest_attempt: bool = True


class HomeworkBatchRegradeItemResult(BaseModel):
    submission_id: int
    status: str  # "queued" | "skipped"
    reason: Optional[str] = None


class HomeworkBatchRegradeResponse(BaseModel):
    queued: int
    skipped: int
    results: list[HomeworkBatchRegradeItemResult] = Field(default_factory=list)


class HomeworkListResponse(BaseModel):
    total: int
    data: List[HomeworkResponse]


class HomeworkSubmissionCreate(BaseModel):
    content: Optional[str] = None
    content_format: ContentFormatLiteral = "markdown"
    attachment_name: Optional[str] = None
    attachment_url: Optional[str] = None
    remove_attachment: bool = False
    used_llm_assist: bool = False
    submission_mode: Literal["full", "feedback_followup"] = "full"
    prior_attempt_id: Optional[int] = None

    @model_validator(mode="after")
    def validate_submission_payload(self):
        self.content = self.content.strip() if isinstance(self.content, str) else self.content
        if not self.content:
            self.content = None
        from apps.backend.courseeval_backend.domains.text_content_format import normalize_content_format

        self.content_format = normalize_content_format(self.content_format)
        if self.submission_mode == "feedback_followup":
            if self.prior_attempt_id is None:
                raise ValueError("按反馈补充提交时必须提供 prior_attempt_id（上一轮提交 id）。")
        else:
            self.prior_attempt_id = None
        if not self.remove_attachment and not (self.content or self.attachment_url):
            raise ValueError("Please provide submission content or an attachment.")
        return self


class HomeworkSubmissionResponse(BaseModel):
    id: int
    homework_id: int
    student_id: int
    subject_id: Optional[int] = None
    class_id: int
    content: Optional[str] = None
    content_format: ContentFormatLiteral = "markdown"
    attachment_name: Optional[str] = None
    attachment_url: Optional[str] = None
    used_llm_assist: bool = False
    submission_mode: Optional[str] = None
    prior_attempt_id: Optional[int] = None
    allow_feedback_followup: bool = False
    submitted_at: datetime
    updated_at: datetime
    student_name: Optional[str] = None
    student_no: Optional[str] = None
    review_score: Optional[float] = None
    review_comment: Optional[str] = None
    latest_attempt_id: Optional[int] = None
    latest_task_status: Optional[str] = None
    latest_task_error: Optional[str] = None
    latest_task_error_code: Optional[str] = None
    latest_task_log: Optional[list[dict[str, Any]]] = None
    appeal_status: Optional[str] = None
    appeal_reason_text: Optional[str] = None
    appeal_teacher_response: Optional[str] = None
    effective_score_attempt_seq: Optional[int] = None
    effective_score_note_zh: str = ""

    model_config = ConfigDict(from_attributes=True)


class HomeworkAttemptResponse(BaseModel):
    id: int
    homework_id: int
    student_id: int
    subject_id: Optional[int] = None
    class_id: int
    submission_summary_id: Optional[int] = None
    content: Optional[str] = None
    content_format: ContentFormatLiteral = "markdown"
    attachment_name: Optional[str] = None
    attachment_url: Optional[str] = None
    is_late: bool = False
    counts_toward_final_score: bool = True
    used_llm_assist: bool = False
    submission_mode: str = "full"
    prior_attempt_id: Optional[int] = None
    submitted_at: datetime
    updated_at: Optional[datetime] = None
    review_score: Optional[float] = None
    review_comment: Optional[str] = None
    task_status: Optional[str] = None
    task_error: Optional[str] = None
    task_error_code: Optional[str] = None
    task_log: Optional[list[dict[str, Any]]] = None
    score_source: Optional[str] = None
    allow_feedback_followup: bool = False

    model_config = ConfigDict(from_attributes=True)


class HomeworkSubmissionHistoryResponse(BaseModel):
    summary: Optional[HomeworkSubmissionResponse] = None
    attempts: List[HomeworkAttemptResponse] = Field(default_factory=list)


class HomeworkSubmissionReviewUpdate(BaseModel):
    attempt_id: Optional[int] = None
    review_score: float = Field(..., ge=0)
    review_comment: Optional[str] = None

    @model_validator(mode="after")
    def normalize_review_payload(self):
        if isinstance(self.review_comment, str):
            self.review_comment = self.review_comment.strip() or None
        return self


class HomeworkSubmissionStatusResponse(BaseModel):
    student_id: int
    student_name: Optional[str] = None
    student_no: Optional[str] = None
    class_name: Optional[str] = None
    submission_id: Optional[int] = None
    status: str
    submitted_at: Optional[datetime] = None
    content: Optional[str] = None
    content_format: ContentFormatLiteral = "markdown"
    content_preview: Optional[str] = None
    attachment_name: Optional[str] = None
    attachment_url: Optional[str] = None
    used_llm_assist: Optional[bool] = None
    review_score: Optional[float] = None
    review_comment: Optional[str] = None
    comment_preview: Optional[str] = None
    latest_attempt_id: Optional[int] = None
    latest_attempt_is_late: Optional[bool] = None
    latest_task_status: Optional[str] = None
    latest_task_error: Optional[str] = None
    latest_task_error_code: Optional[str] = None
    latest_task_log: Optional[list[dict[str, Any]]] = None
    attempt_count: int = 0
    appeal_status: Optional[str] = None
    appeal_reason_text: Optional[str] = None
    appeal_teacher_response: Optional[str] = None
    effective_score_attempt_seq: Optional[int] = None
    effective_score_note_zh: str = ""


class HomeworkSubmissionStatusListResponse(BaseModel):
    total: int
    page: int = 1
    page_size: int = 20
    data: List[HomeworkSubmissionStatusResponse]


class HomeworkGradeAppealCreate(BaseModel):
    reason_text: str = Field(..., min_length=10, max_length=8000)

    @field_validator("reason_text")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        t = (value or "").strip()
        if len(t) < 10:
            raise ValueError("申诉理由至少 10 个字符。")
        return t


class HomeworkGradeAppealResponse(BaseModel):
    id: int
    homework_id: int
    student_id: int
    submission_id: int
    reason_text: str
    status: str
    teacher_response: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class HomeworkGradeAppealTeacherUpdate(BaseModel):
    teacher_response: str = Field(..., min_length=1)
    status: str = Field(default="resolved")

    @field_validator("teacher_response")
    @classmethod
    def strip_teacher_response(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("教师回复不能为空。")
        return text


class StudentHomeworkRowResponse(BaseModel):
    homework_id: int
    title: str
    due_date: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    review_score: Optional[float] = None
    attempt_count: int = 0
    latest_task_status: Optional[str] = None
    submission_id: Optional[int] = None
    appeal_status: Optional[str] = None
    appeal_teacher_response: Optional[str] = None


class StudentHomeworkListResponse(BaseModel):
    total: int
    page: int = 1
    page_size: int = 20
    data: List[StudentHomeworkRowResponse]


class HomeworkSubmissionDownloadRequest(BaseModel):
    submission_ids: List[int]


class HomeworkRegradeRequest(BaseModel):
    attempt_id: Optional[int] = None


class LLMEndpointPresetBase(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    name: str
    base_url: str = "https://yunwu.ai/v1"
    api_key: str = ""
    model_name: str = "gpt-5.4"
    connect_timeout_seconds: int = Field(default=30, ge=1, le=300)
    read_timeout_seconds: int = Field(default=180, ge=1, le=600)
    max_retries: int = Field(default=3, ge=0, le=10)
    initial_backoff_seconds: int = Field(default=5, ge=1, le=120)
    is_active: bool = True


class LLMEndpointPresetCreate(LLMEndpointPresetBase):
    pass


class LLMEndpointPresetUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    connect_timeout_seconds: Optional[int] = Field(default=None, ge=1, le=300)
    read_timeout_seconds: Optional[int] = Field(default=None, ge=1, le=600)
    max_retries: Optional[int] = Field(default=None, ge=0, le=10)
    initial_backoff_seconds: Optional[int] = Field(default=None, ge=1, le=120)
    is_active: Optional[bool] = None


class LLMEndpointPresetResponse(BaseModel):
    id: int
    name: str
    base_url: str
    model_name: str
    connect_timeout_seconds: int
    read_timeout_seconds: int
    max_retries: int
    initial_backoff_seconds: int
    is_active: bool
    supports_vision: bool
    validation_status: str
    validation_message: Optional[str] = None
    text_validation_status: Optional[str] = None
    text_validation_message: Optional[str] = None
    vision_validation_status: Optional[str] = None
    vision_validation_message: Optional[str] = None
    validated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CourseLLMConfigEndpointSelection(BaseModel):
    preset_id: int
    priority: int = Field(default=1, ge=1)


class LLMGroupMemberSelection(BaseModel):
    preset_id: int
    priority: int = Field(default=1, ge=1)


class LLMGroupSelection(BaseModel):
    priority: int = Field(default=1, ge=1)
    name: Optional[str] = None
    members: List[LLMGroupMemberSelection] = Field(default_factory=list)


class CourseLLMConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    is_enabled: bool = False
    response_language: Optional[str] = None
    max_input_tokens: int = Field(default=16000, ge=1000)
    max_output_tokens: Optional[int] = Field(default=None, ge=1)
    system_prompt: Optional[str] = None
    teacher_prompt: Optional[str] = None
    endpoints: List[CourseLLMConfigEndpointSelection] = Field(default_factory=list)
    groups: List[LLMGroupSelection] = Field(default_factory=list)
    # When the client sends only flat "endpoints" and empty "groups" (e.g. teacher UI), do not wipe an
    # existing group-based routing that was set via API/DB. Set true to force flat rebind and drop groups.
    replace_group_routing_with_flat_endpoints: bool = False


class CourseLLMConfigEndpointResponse(BaseModel):
    id: int
    preset_id: int
    priority: int
    group_id: Optional[int] = None
    preset_name: Optional[str] = None
    model_name: Optional[str] = None
    validation_status: Optional[str] = None
    supports_vision: Optional[bool] = None


class LLMGroupResponse(BaseModel):
    id: int
    priority: int
    name: Optional[str] = None
    members: List[CourseLLMConfigEndpointResponse] = Field(default_factory=list)


class CourseLLMConfigResponse(BaseModel):
    id: Optional[int] = None
    subject_id: int
    is_enabled: bool = False
    response_language: Optional[str] = None
    max_input_tokens: int = 16000
    max_output_tokens: Optional[int] = None
    system_prompt: Optional[str] = None
    teacher_prompt: Optional[str] = None
    endpoints: List[CourseLLMConfigEndpointResponse] = Field(default_factory=list)
    groups: List[LLMGroupResponse] = Field(default_factory=list)
    visual_validation_notice: str
    quota_usage: Optional[dict] = None


class CourseMaterialPlacement(BaseModel):
    section_id: int
    chapter_id: int
    chapter_title: str
    sort_order: int


class CourseMaterialBase(BaseModel):
    title: str
    content: Optional[str] = None
    content_format: ContentFormatLiteral = "markdown"
    attachment_name: Optional[str] = None
    attachment_url: Optional[str] = None
    class_id: int
    subject_id: Optional[int] = None
    chapter_ids: Optional[List[int]] = None

    @field_validator("content_format", mode="before")
    @classmethod
    def validate_material_content_format(cls, value):
        from apps.backend.courseeval_backend.domains.text_content_format import normalize_content_format

        return normalize_content_format(value if isinstance(value, str) else None)


class CourseMaterialCreate(CourseMaterialBase):
    pass


class CourseMaterialUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    content_format: Optional[ContentFormatLiteral] = None
    attachment_name: Optional[str] = None
    attachment_url: Optional[str] = None
    remove_attachment: bool = False
    chapter_ids: Optional[List[int]] = None

    @field_validator("content_format", mode="before")
    @classmethod
    def validate_material_update_content_format(cls, value):
        if value is None:
            return None
        from apps.backend.courseeval_backend.domains.text_content_format import normalize_content_format

        return normalize_content_format(value if isinstance(value, str) else None)


class CourseMaterialResponse(CourseMaterialBase):
    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime
    class_name: Optional[str] = None
    subject_name: Optional[str] = None
    creator_name: Optional[str] = None
    placements: List[CourseMaterialPlacement] = Field(default_factory=list)
    discussion_requires_context: bool = False

    model_config = ConfigDict(from_attributes=True)


class CourseMaterialListResponse(BaseModel):
    total: int
    data: List[CourseMaterialResponse]


class CourseMaterialHomeworkLinkResponse(BaseModel):
    link_id: int
    homework_id: int
    title: str
    subject_id: Optional[int] = None
    subject_name: Optional[str] = None
    class_id: Optional[int] = None
    class_name: Optional[str] = None
    due_date: Optional[datetime] = None
    created_at: Optional[datetime] = None
    sort_order: int


class CourseMaterialChapterNode(BaseModel):
    id: int
    subject_id: int
    parent_id: Optional[int] = None
    title: str
    sort_order: int
    is_uncategorized: bool
    homework_links: List[CourseMaterialHomeworkLinkResponse] = Field(default_factory=list)
    children: List["CourseMaterialChapterNode"] = Field(default_factory=list)


class CourseMaterialChapterTreeResponse(BaseModel):
    nodes: List[CourseMaterialChapterNode]


class CourseMaterialChapterCreate(BaseModel):
    title: str
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None


class CourseMaterialChapterUpdate(BaseModel):
    title: Optional[str] = None


class CourseMaterialChapterReorderRequest(BaseModel):
    parent_id: Optional[int] = None
    ordered_chapter_ids: List[int]


class CourseMaterialSectionReorderRequest(BaseModel):
    chapter_id: int
    ordered_section_ids: List[int]


class CourseMaterialAddPlacementRequest(BaseModel):
    chapter_id: int


class CourseMaterialHomeworkLinkCreate(BaseModel):
    chapter_id: int
    homework_id: int


CourseMaterialChapterNode.model_rebuild()
LearningNoteChapterNode.model_rebuild()
DashboardStats.model_rebuild(_types_namespace={"ScoreResponse": ScoreResponse})
