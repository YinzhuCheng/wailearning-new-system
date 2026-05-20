<template>
  <div class="courses-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ pageTitle }}</h1>
        <p class="page-subtitle">{{ pageSubtitle }}</p>
      </div>
      <el-button
        v-if="showManageActions"
        type="primary"
        data-testid="subjects-open-create"
        @click="openCreateDialog"
      >
        新建课程
      </el-button>
    </div>

    <el-empty
      v-if="isClassTeacherView && !currentClassId"
      description="当前班主任账号没有绑定班级。"
    />

    <template v-else-if="isClassTeacherView">
      <el-card shadow="never">
        <DualHorizontalScroll target-selector=".courses-table-scroll">
          <div class="courses-table-scroll dual-scroll-target">
            <el-table :data="classTeacherCourses" v-loading="loading">
          <el-table-column prop="name" label="课程名称" min-width="180" />
          <el-table-column prop="teacher_name" label="任课老师" width="160" />
          <el-table-column prop="class_name" label="班级" width="160" />
          <el-table-column label="课程类型" width="120">
            <template #default="{ row }">
              <el-tag :type="row.course_type === 'elective' ? 'warning' : 'success'">
                {{ row.course_type === 'elective' ? '选修课' : '必修课' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="row.status === 'completed' ? 'info' : 'primary'">
                {{ row.status === 'completed' ? '已结课' : '进行中' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="semester" label="学期" width="140" />
          <el-table-column label="课程时间" min-width="320">
            <template #default="{ row }">
              <div v-if="getCourseTimeLines(row).length" class="course-time-list">
                <div
                  v-for="(line, index) in getCourseTimeLines(row)"
                  :key="`${row.id}-${index}`"
                  class="course-time-line"
                >
                  {{ line }}
                </div>
              </div>
              <span v-else>未设置</span>
            </template>
          </el-table-column>
          <el-table-column prop="student_count" label="学生数" width="100" />
          <el-table-column label="操作" width="280" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" size="small" @click="openCourseDetail(row)">
                课程详细
              </el-button>
              <el-button type="success" size="small" @click="openEditDialog(row)">编辑</el-button>
              <el-button type="success" size="small" :data-testid="`subjects-open-llm-${row.id}`" @click="openLlmConfigDialog(row)">
                LLM 配置
              </el-button>
            </template>
          </el-table-column>
            </el-table>
          </div>
        </DualHorizontalScroll>
      </el-card>

      <el-dialog
        v-model="courseDetailVisible"
        title="课程详细"
        width="880px"
        destroy-on-close
      >
        <div v-if="detailCourse" class="course-detail-meta">
          <div><strong>课程：</strong>{{ detailCourse.name }}</div>
          <div><strong>班级：</strong>{{ detailCourse.class_name || currentClassName }}</div>
          <div><strong>任课老师：</strong>{{ detailCourse.teacher_name || '未安排教师' }}</div>
        </div>

        <DualHorizontalScroll target-selector=".courses-detail-scroll">
          <div class="courses-detail-scroll dual-scroll-target">
            <el-table :data="courseDetailRows" v-loading="courseDetailLoading">
          <el-table-column prop="student_name" label="学生姓名" min-width="150" />
          <el-table-column prop="student_no" label="学号" min-width="160" />
          <el-table-column prop="absence_count" label="缺勤次数" width="120" />
          <el-table-column prop="missing_homework_count" label="缺交次数" width="120" />
          <el-table-column prop="final_score_text" label="最终成绩" width="140" />
            </el-table>
          </div>
        </DualHorizontalScroll>

        <template v-if="detailCourse?.class_id || (detailCourse?.class_links && detailCourse.class_links.length)" #footer>
          <div class="course-detail-footer">
            <el-button @click="courseDetailVisible = false">关闭</el-button>
            <el-button type="warning" plain @click="openRosterEnrollFromDetail">从花名册进课…</el-button>
          </div>
        </template>
      </el-dialog>
    </template>

    <template v-else>
      <el-card shadow="never">
        <DualHorizontalScroll target-selector=".courses-table-scroll">
          <div class="courses-table-scroll dual-scroll-target">
            <el-table :data="courses" v-loading="loading">
          <el-table-column prop="name" label="课程名称" min-width="180" />
          <el-table-column prop="class_name" label="班级" width="160" />
          <el-table-column prop="teacher_name" label="任课老师" width="160" />
          <el-table-column label="课程类型" width="120">
            <template #default="{ row }">
              <el-tag :type="row.course_type === 'elective' ? 'warning' : 'success'">
                {{ row.course_type === 'elective' ? '选修课' : '必修课' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="row.status === 'completed' ? 'info' : 'primary'">
                {{ row.status === 'completed' ? '已结课' : '进行中' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="semester" label="学期" width="140" />
          <el-table-column label="课程时间" min-width="360">
            <template #default="{ row }">
              <div v-if="getCourseTimeLines(row).length" class="course-time-list">
                <div
                  v-for="(line, index) in getCourseTimeLines(row)"
                  :key="`${row.id}-${index}`"
                  class="course-time-line"
                >
                  {{ line }}
                </div>
              </div>
              <span v-else>未设置</span>
            </template>
          </el-table-column>
          <el-table-column prop="student_count" label="学生数" width="100" />
          <el-table-column prop="description" label="课程简介" min-width="220" show-overflow-tooltip />
          <el-table-column label="操作" width="300" fixed="right">
            <template #default="{ row }">
              <el-button
                type="success"
                size="small"
                plain
                :data-testid="`btn-roster-enroll-${row.id}`"
                @click="openRosterEnrollDialog(row)"
              >
                从花名册进课
              </el-button>
              <el-button type="primary" size="small" @click="openEditDialog(row)">编辑</el-button>
              <el-button type="success" size="small" :data-testid="`subjects-open-llm-${row.id}`" @click="openLlmConfigDialog(row)">LLM 配置</el-button>
              <el-button type="danger" size="small" :data-testid="`subjects-delete-${row.id}`" @click="deleteCourse(row)">删除</el-button>
            </template>
          </el-table-column>
            </el-table>
          </div>
        </DualHorizontalScroll>
      </el-card>

      <el-dialog
        v-model="dialogVisible"
        :title="editingCourse ? '编辑课程' : '新建课程'"
        width="960px"
        destroy-on-close
      >
        <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
          <el-form-item label="课程名称" prop="name">
            <el-input v-model="form.name" data-testid="subjects-form-name" />
          </el-form-item>
          <el-form-item label="任课老师" prop="teacher_id">
            <el-select v-model="form.teacher_id" placeholder="请选择任课老师" style="width: 100%" clearable>
              <el-option v-for="item in teachers" :key="item.id" :label="item.real_name" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="课程类型" prop="course_type">
            <el-radio-group v-model="form.course_type">
              <el-radio label="required">必修课</el-radio>
              <el-radio label="elective">选修课</el-radio>
            </el-radio-group>
          </el-form-item>

          <template v-if="form.course_type === 'elective'">
            <el-alert type="info" :closable="false" show-icon class="subject-elective-hint">
              选修课不按行政班绑定；课程列表「班级」列显示为「-」。学生可在选课目录中自愿选课。
            </el-alert>
          </template>

          <el-form-item v-else label="行政班级" prop="class_links">
            <div class="class-links-editor">
              <div v-for="(row, idx) in form.class_links" :key="`cl-${idx}`" class="class-link-row">
                <el-select v-model="row.class_id" placeholder="选择班级" filterable style="width: 220px">
                  <el-option v-for="item in classes" :key="item.id" :label="item.name" :value="item.id" />
                </el-select>
                <el-radio-group v-model="row.enrollment_mode" class="class-link-mode">
                  <el-radio label="all_in_class">全班自动进课</el-radio>
                  <el-radio label="roster_subset">按花名册选部分进课</el-radio>
                </el-radio-group>
                <el-button
                  v-if="form.class_links.length > 1"
                  text
                  type="danger"
                  @click="removeClassLinkRow(idx)"
                >
                  移除
                </el-button>
              </div>
              <el-button plain size="small" class="class-links-editor__add" @click="addClassLinkRow">
                添加班级
              </el-button>
              <p class="hint muted">
                必修课可对应多个行政班；「全班自动」会与各班花名册对齐；「按花名册选部分」仅通过「从花名册进课」手动勾选。
              </p>
            </div>
          </el-form-item>

          <el-form-item label="课程状态" prop="status">
            <el-radio-group v-model="form.status">
              <el-radio label="active">进行中</el-radio>
              <el-radio label="completed">已结课</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="所属学期" prop="semester_id">
            <el-select v-model="form.semester_id" placeholder="请选择学期" style="width: 100%" clearable>
              <el-option v-for="item in semesters" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
          </el-form-item>

          <el-form-item label="课程时间" prop="course_times" class="course-times-form-item">
            <div class="course-times-editor">
              <div
                v-for="(courseTime, index) in form.course_times"
                :key="`course-time-${index}`"
                class="course-time-panel"
              >
                <div class="course-time-panel__header">
                  <div>
                    <div class="course-time-panel__title">课程时间 {{ index + 1 }}</div>
                    <div class="course-time-panel__subtitle">
                      设置这一段时间内的起始日期、结束日期和每周上课时间
                    </div>
                  </div>
                  <el-button
                    v-if="form.course_times.length > 1"
                    text
                    type="danger"
                    @click="removeCourseTime(index)"
                  >
                    删除
                  </el-button>
                </div>

                <div class="course-time-panel__fields">
                  <el-form-item :prop="`course_times.${index}.course_start_at`" label="开始日期" label-width="80px">
                    <el-date-picker
                      v-model="courseTime.course_start_at"
                      type="date"
                      placeholder="请选择开始日期"
                      style="width: 100%"
                      value-format="YYYY-MM-DD"
                    />
                  </el-form-item>

                  <el-form-item :prop="`course_times.${index}.course_end_at`" label="结束日期" label-width="80px">
                    <el-date-picker
                      v-model="courseTime.course_end_at"
                      type="date"
                      placeholder="请选择结束日期"
                      style="width: 100%"
                      value-format="YYYY-MM-DD"
                    />
                  </el-form-item>
                </div>

                <div class="course-time-panel__schedule">
                  <div class="course-time-panel__schedule-label">每周时间</div>
                  <CourseSchedulePicker v-model="courseTime.weekly_schedule" />
                </div>
              </div>

              <el-button plain class="course-times-editor__add" @click="addCourseTime">
                添加课程时间
              </el-button>
            </div>
          </el-form-item>

          <el-form-item label="课程简介" prop="description">
            <el-input v-model="form.description" type="textarea" :rows="4" />
          </el-form-item>
          <el-form-item label="课程封面">
            <div class="cover-field">
              <el-image
                v-if="coverPreviewSrc"
                :src="coverPreviewSrc"
                fit="cover"
                class="cover-preview"
              />
              <div v-else class="cover-preview cover-preview--empty">无封面</div>
              <div class="cover-actions">
                <input
                  ref="coverFileInputRef"
                  type="file"
                  accept="image/jpeg,image/png,image/gif,image/webp,image/bmp,image/svg+xml,.jpg,.jpeg,.png,.gif,.webp,.bmp,.svg"
                  class="cover-file-input"
                  @change="onCoverFileChange"
                />
                <el-button size="small" data-testid="subjects-course-cover-pick" @click="triggerCoverPick">选择图片</el-button>
                <el-button
                  v-if="showCoverRemove"
                  size="small"
                  type="danger"
                  plain
                  @click="clearCover"
                >
                  移除封面
                </el-button>
                <p class="cover-hint">JPG / PNG / GIF / WebP / BMP / SVG，单张不超过 10MB。留空则选课与资料区保持原样布局。</p>
              </div>
            </div>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" data-testid="subjects-course-save" :loading="submitting" @click="submitForm">
            保存
          </el-button>
        </template>
      </el-dialog>

      <el-dialog
        v-model="rosterEnrollVisible"
        data-testid="dialog-roster-enroll"
        :title="rosterEnrollCourse ? `从花名册进课 · ${rosterEnrollCourse.name}` : '从花名册进课'"
        width="820px"
        destroy-on-close
        @closed="resetRosterEnrollDialog"
      >
        <el-alert type="warning" :closable="false" class="roster-enroll-alert">
          <template #title>与花名册一致</template>
          <p class="roster-enroll-alert-body">
            仅允许将<strong>本课程已绑定行政班花名册</strong>中的学生加入选课。
            必修课若绑定多个班级，请先选择要操作的班级再勾选学生。
            需要<strong>全班</strong>与花名册对齐时，请点「全班加入选课」（仅对标记为「全班自动进课」的班级生效）；部分进课请勾选后点「加入选课」。
          </p>
        </el-alert>

        <el-empty v-if="rosterEnrollCourse && !rosterLinkOptions.length" description="当前课程未绑定行政班，无法从花名册进课。" />

        <template v-else>
          <div v-if="rosterEnrollCourse && rosterLinkOptions.length > 1" class="roster-enroll-pick-class">
            <span class="muted">花名册班级：</span>
            <el-select v-model="rosterPickClassId" placeholder="选择班级" style="width: 260px">
              <el-option v-for="opt in rosterLinkOptions" :key="opt.id" :label="opt.name" :value="opt.id" />
            </el-select>
          </div>
          <div v-if="rosterEnrollCourse" class="roster-enroll-meta">
            <span>当前班级：{{ rosterSelectedClassLabel }}</span>
          </div>

          <DualHorizontalScroll target-selector=".courses-roster-scroll">
            <div class="courses-roster-scroll dual-scroll-target">
              <el-table
                ref="rosterEnrollTableRef"
                data-testid="table-roster-enroll-pick"
                :data="rosterEnrollRows"
                v-loading="rosterEnrollLoading"
                max-height="420"
                row-key="id"
                @selection-change="onRosterEnrollSelectionChange"
              >
                <el-table-column type="selection" width="48" :selectable="row => !row._enrolled" />
                <el-table-column prop="name" label="姓名" min-width="120" />
                <el-table-column prop="student_no" label="学号" min-width="140" />
                <el-table-column label="选课状态" width="120">
                  <template #default="{ row }">
                    <el-tag v-if="row._enrolled" type="success" size="small">已在课</el-tag>
                    <el-tag v-else type="info" size="small">未在课</el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </DualHorizontalScroll>
        </template>

        <template #footer>
          <el-button @click="rosterEnrollVisible = false">取消</el-button>
          <el-button
            v-if="userStore.isAdmin && rosterLinkOptions.length"
            type="warning"
            plain
            data-testid="btn-roster-enroll-all-class"
            :loading="rosterEnrollSubmitting"
            :disabled="rosterEnrollLoading"
            @click="submitRosterEnrollAllFromClass"
          >
            全班加入选课
          </el-button>
          <el-button
            type="primary"
            data-testid="btn-roster-enroll-submit"
            :loading="rosterEnrollSubmitting"
            :disabled="!rosterEnrollSelection.length || rosterEnrollLoading"
            @click="submitRosterEnroll"
          >
            加入选课
          </el-button>
        </template>
      </el-dialog>

      <el-dialog
        v-model="llmDialogVisible"
        data-testid="dialog-course-llm"
        :title="llmDialogCourse ? `${llmDialogCourse.name} · LLM 配置` : 'LLM 配置'"
        width="960px"
        destroy-on-close
      >
        <el-form v-if="llmDialogCourse" :model="llmForm" label-width="140px" v-loading="llmLoading">
          <el-alert
            class="llm-notice"
            type="info"
            :closable="false"
            :title="llmVisualValidationNotice"
          />

          <el-form-item label="启用自动评分">
            <el-switch v-model="llmForm.is_enabled" data-testid="llm-course-enable" />
          </el-form-item>

          <el-form-item label="响应语言">
            <el-input v-model="llmForm.response_language" placeholder="例如 zh-CN / en-US，可为空" />
          </el-form-item>

          <el-form-item label="输入 token 上限">
            <el-input-number v-model="llmForm.max_input_tokens" :min="1000" :step="1000" style="width: 100%" />
          </el-form-item>

          <el-form-item label="输出 token 上限">
            <el-input-number v-model="llmForm.max_output_tokens" :min="1" :step="100" style="width: 100%" />
            <div class="attachment-help">留空表示不限制输出长度。</div>
          </el-form-item>

          <el-alert
            v-if="llmQuotaUsage && llmQuotaUsage.usage_date"
            class="llm-notice"
            type="info"
            :closable="false"
            :title="`系统 LLM 用量统计日：${llmQuotaUsage.usage_date}（${llmQuotaUsage.quota_timezone}）`"
          />
          <div v-if="llmForm.is_enabled" class="attachment-help" style="margin-bottom: 12px">
            自动评分会将作业说明、学生文字与附件解析结果分段送入模型；大附件、PDF 多页或 zip 可能被截断或跳过。学生个人日
            token 由管理员在系统设置中统一配置；本课只保留自动评分开关、单次调用边界、端点顺序和提示词。并发任务数由管理员在系统设置中配置。若本课尚未选择端点，保存或打开配置时会尝试从其他已配置且校验通过的课程自动同步一份模板。
          </div>

          <el-form-item label="系统提示词">
            <el-input v-model="llmForm.system_prompt" type="textarea" :rows="5" placeholder="可选。若为空则使用系统默认提示词。" />
          </el-form-item>

          <el-form-item label="教师提示词">
            <el-input v-model="llmForm.teacher_prompt" type="textarea" :rows="5" placeholder="可选。可补充课程评分偏好、风格与要求。" />
          </el-form-item>

          <el-form-item
            v-if="llmForm.groups && llmForm.groups.length"
            label="组级路由"
          >
            <el-alert
              class="llm-notice"
              type="success"
              :closable="false"
              show-icon
              title="本课程已配置多组/故障转移路由。下方仅可编辑「平铺顺序」以外的选项；若需改为仅平铺端点，请联系管理员在保存接口中显式设置。"
            />
            <ul class="llm-group-list">
              <li
                v-for="(g, gi) in llmForm.groups"
                :key="`g-${gi}`"
              >
                <strong>{{ g.name || `组 ${g.priority || gi + 1}` }}</strong>（顺序 {{ g.priority }})
                <ol>
                  <li
                    v-for="(m, mi) in (g.members || [])"
                    :key="`m-${gi}-${mi}`"
                  >
                    端点 #{{ m.preset_id }} · 优先级 {{ m.priority }}
                  </li>
                </ol>
              </li>
            </ul>
            <p class="llm-group-hint">保存本对话框时，不会清除上述组级配置；只更新开关、预算与提示词等字段。</p>
          </el-form-item>

          <el-form-item v-show="!llmForm.groups || !llmForm.groups.length" label="端点顺序">
            <div class="llm-endpoints">
              <el-empty v-if="!llmPresets.length" description="暂无可用端点，请先由管理员创建并完成视觉校验。" />
              <div
                v-for="preset in llmPresets"
                :key="preset.id"
                class="llm-endpoint-row"
                :data-testid="`llm-course-preset-row-${preset.id}`"
              >
                <el-checkbox
                  :data-testid="`llm-course-preset-toggle-${preset.id}`"
                  :model-value="isPresetSelected(preset.id)"
                  :disabled="preset.validation_status !== 'validated' || !preset.supports_vision"
                  @change="checked => togglePresetSelection(preset, checked)"
                >
                  <div class="llm-endpoint-meta">
                    <strong>{{ preset.name }}</strong>
                    <span>{{ preset.model_name }}</span>
                    <span class="llm-validate-pills">
                      文本<el-tag size="small" :type="llmStepTagType(preset.text_validation_status)">{{ llmStepLabel(preset.text_validation_status) }}</el-tag>
                      视觉<el-tag size="small" :type="llmStepTagType(preset.vision_validation_status)">{{ llmStepLabel(preset.vision_validation_status) }}</el-tag>
                    </span>
                    <span v-if="llmPresetDetailLine(preset)" class="llm-validate-detail">{{ llmPresetDetailLine(preset) }}</span>
                  </div>
                </el-checkbox>

                <el-input-number
                  v-if="isPresetSelected(preset.id)"
                  :data-testid="`llm-course-preset-priority-${preset.id}`"
                  :model-value="getPresetPriority(preset.id)"
                  :min="1"
                  @update:model-value="value => updatePresetPriority(preset.id, value)"
                />
              </div>
            </div>
          </el-form-item>
        </el-form>

        <template #footer>
          <el-button @click="llmDialogVisible = false">取消</el-button>
          <el-button type="primary" data-testid="llm-course-save" :loading="llmSaving" @click="saveLlmConfig">保存配置</el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import api from '@/api'
import CourseSchedulePicker from '@/components/CourseSchedulePicker.vue'
import DualHorizontalScroll from '@/components/DualHorizontalScroll.vue'
import { useUserStore } from '@/stores/user'
import {
  filterCoursesByClassId,
  resolveClassTeacherClassId,
  resolveClassTeacherClassName
} from '@/utils/classTeacher'
import { loadAllPages } from '@/utils/pagedFetch'
import { parseScheduleValue } from '@/utils/courseSchedule'
import {
  createEmptyCourseTime,
  formatCourseTimeEntry,
  normalizeEditableCourseTimes,
  serializeCourseTimesPayload
} from '@/utils/courseTimes'

const userStore = useUserStore()

const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const editingCourse = ref(null)
const formRef = ref(null)
const coverFileInputRef = ref(null)
const courseDetailVisible = ref(false)
const courseDetailLoading = ref(false)
const detailCourse = ref(null)
const llmDialogVisible = ref(false)
const llmDialogCourse = ref(null)
const llmLoading = ref(false)
const llmSaving = ref(false)
const llmPresets = ref([])
const llmVisualValidationNotice = ref('端点需由管理员在系统设置中完成「文本+视觉」校验；视觉校验收需要上传测试图。只有通过视觉能力校验的端点，才能加入本课程并用于带图作业自动评分。')
const llmQuotaUsage = ref(null)

const courses = ref([])
const classes = ref([])
const teachers = ref([])
const semesters = ref([])
const classTeacherCoursePool = ref([])
const courseDetailRows = ref([])

const rosterEnrollVisible = ref(false)
const rosterEnrollCourse = ref(null)
const rosterEnrollLoading = ref(false)
const rosterEnrollSubmitting = ref(false)
const rosterEnrollRows = ref([])
const rosterEnrollSelection = ref([])
const rosterEnrollTableRef = ref(null)
const rosterPickClassId = ref(null)

const rosterLinkOptions = computed(() => {
  const c = rosterEnrollCourse.value
  if (!c) return []
  if (c.course_type === 'elective') {
    return (classes.value || []).map(cl => ({
      id: cl.id,
      name: cl.name || `班级 #${cl.id}`
    }))
  }
  if (Array.isArray(c.class_links) && c.class_links.length) {
    return c.class_links.map(l => ({
      id: l.class_id,
      name: l.class_name || `班级 #${l.class_id}`
    }))
  }
  if (c.class_id) {
    return [{ id: c.class_id, name: c.class_name || `班级 #${c.class_id}` }]
  }
  return []
})

const rosterSelectedClassLabel = computed(() => {
  const id = rosterPickClassId.value
  const hit = rosterLinkOptions.value.find(o => Number(o.id) === Number(id))
  return hit?.name || '—'
})

const llmForm = reactive({
  is_enabled: false,
  response_language: '',
  max_input_tokens: 16000,
  max_output_tokens: null,
  system_prompt: '',
  teacher_prompt: '',
  endpoints: [],
  // API-only group routing: shown read-only; saving flat endpoints will not clear it unless you switch to flat-only save path
  groups: []
})

const normalizeNullableNumber = value => {
  if (value === '' || value === null || value === undefined) {
    return null
  }
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

const llmStepLabel = s => {
  if (s === 'passed') return '通过'
  if (s === 'failed') return '失败'
  if (s === 'skipped') return '跳过'
  return '未测'
}

const llmStepTagType = s => {
  if (s === 'passed') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'skipped') return 'info'
  return 'info'
}

const llmPresetDetailLine = p => {
  if (!p) {
    return ''
  }
  const t = p.text_validation_message
  const v = p.vision_validation_message
  if (!t && !v) {
    return p.validation_message || ''
  }
  return [t ? `文本：${t}` : null, v ? `视觉：${v}` : null].filter(Boolean).join('；')
}

const isClassTeacherView = computed(() => userStore.isClassTeacher)
const currentClassId = computed(() => resolveClassTeacherClassId(userStore.userInfo, classTeacherCoursePool.value))
const currentClassName = computed(() => resolveClassTeacherClassName(userStore.userInfo, classTeacherCoursePool.value) || '未分配班级')
const classTeacherCourses = computed(() => filterCoursesByClassId(classTeacherCoursePool.value, currentClassId.value))
const showManageActions = computed(() => !isClassTeacherView.value)

const pageTitle = computed(() => (isClassTeacherView.value ? '课程信息' : '课程管理'))
const pageSubtitle = computed(() => {
  if (isClassTeacherView.value) {
    return currentClassId.value ? `${currentClassName.value} 全部课程信息；班主任可编辑课程目录、封面与 LLM 配置（与任课教师、管理员共享后端权限）。` : '请先为班主任账号分配班级。'
  }

  return '管理员可统一查看、编辑课程信息与课程时间安排。'
})

const createEmptyClassLink = () => ({
  class_id: null,
  enrollment_mode: 'all_in_class'
})

const form = reactive({
  name: '',
  class_links: [createEmptyClassLink()],
  teacher_id: null,
  semester_id: null,
  course_type: 'required',
  status: 'active',
  course_times: [createEmptyCourseTime()],
  description: ''
})

const coverOriginalUrl = ref('')
const pendingCoverFile = ref(null)
const localCoverPreviewUrl = ref('')

const revokeLocalCoverPreview = () => {
  if (localCoverPreviewUrl.value) {
    try {
      URL.revokeObjectURL(localCoverPreviewUrl.value)
    } catch {
      /* ignore */
    }
    localCoverPreviewUrl.value = ''
  }
}

const coverPreviewSrc = computed(() => {
  if (localCoverPreviewUrl.value) return localCoverPreviewUrl.value
  return coverOriginalUrl.value || ''
})

const showCoverRemove = computed(() => Boolean(coverOriginalUrl.value || pendingCoverFile.value))

const validateCourseTimes = (_rule, value, callback) => {
  if (!Array.isArray(value) || !value.length) {
    callback(new Error('请至少添加一组课程时间'))
    return
  }

  for (const item of value) {
    if (!item.course_start_at || !item.course_end_at) {
      callback(new Error('请为每组课程时间选择开始日期和结束日期'))
      return
    }

    if (new Date(item.course_end_at) < new Date(item.course_start_at)) {
      callback(new Error('课程时间的结束日期不能早于开始日期'))
      return
    }

    if (!parseScheduleValue(item.weekly_schedule).length) {
      callback(new Error('请为每组课程时间选择每周时间'))
      return
    }
  }

  callback()
}

const addClassLinkRow = () => {
  form.class_links.push(createEmptyClassLink())
}

const removeClassLinkRow = index => {
  if (form.class_links.length <= 1) {
    return
  }
  form.class_links.splice(index, 1)
}

const validateClassLinks = (_rule, value, callback) => {
  if (form.course_type !== 'required') {
    callback()
    return
  }
  if (!Array.isArray(value) || !value.length) {
    callback(new Error('请至少绑定一个行政班级'))
    return
  }
  for (const row of value) {
    if (!row.class_id) {
      callback(new Error('请为每一行选择班级'))
      return
    }
  }
  callback()
}

const rules = {
  name: [{ required: true, message: '请输入课程名称', trigger: 'blur' }],
  class_links: [{ validator: validateClassLinks, trigger: 'change' }],
  course_type: [{ required: true, message: '请选择课程类型', trigger: 'change' }],
  status: [{ required: true, message: '请选择课程状态', trigger: 'change' }],
  course_times: [{ validator: validateCourseTimes, trigger: 'change' }]
}

const resetForm = () => {
  revokeLocalCoverPreview()
  pendingCoverFile.value = null
  coverOriginalUrl.value = ''
  if (coverFileInputRef.value) {
    coverFileInputRef.value.value = ''
  }
  Object.assign(form, {
    name: '',
    class_links: [createEmptyClassLink()],
    teacher_id: null,
    semester_id: null,
    course_type: 'required',
    status: 'active',
    course_times: [createEmptyCourseTime()],
    description: ''
  })
}

const loadCourses = async () => {
  loading.value = true
  try {
    if (isClassTeacherView.value) {
      classTeacherCoursePool.value = await userStore.fetchTeachingCourses(true)
      return
    }

    courses.value = await api.courses.list()
  } finally {
    loading.value = false
  }
}

const resetRosterEnrollDialog = () => {
  rosterEnrollCourse.value = null
  rosterEnrollRows.value = []
  rosterEnrollSelection.value = []
  rosterPickClassId.value = null
  rosterEnrollTableRef.value?.clearSelection?.()
}

const loadRosterRowsForPick = async () => {
  const course = rosterEnrollCourse.value
  const cid = rosterPickClassId.value
  rosterEnrollRows.value = []
  rosterEnrollSelection.value = []
  rosterEnrollTableRef.value?.clearSelection?.()

  if (!course?.id || !cid) {
    return
  }

  rosterEnrollLoading.value = true
  try {
    const [roster, enrolled] = await Promise.all([
      loadAllPages(params =>
        api.students.list({
          ...params,
          class_id: cid,
          page_size: 500
        })
      ),
      api.courses.getStudents(course.id)
    ])
    const enrolledIds = new Set((enrolled || []).map(r => r.student_id))
    rosterEnrollRows.value = (roster || []).map(row => ({
      ...row,
      _enrolled: enrolledIds.has(row.id)
    }))
  } catch (error) {
    console.error('加载花名册失败', error)
  } finally {
    rosterEnrollLoading.value = false
  }
}

const openRosterEnrollDialog = async course => {
  rosterEnrollCourse.value = course
  rosterEnrollVisible.value = true
  rosterEnrollRows.value = []
  rosterEnrollSelection.value = []

  await nextTick()
  const opts = rosterLinkOptions.value
  rosterPickClassId.value = opts[0]?.id ?? null
  await loadRosterRowsForPick()
}

const onRosterEnrollSelectionChange = rows => {
  rosterEnrollSelection.value = rows
}

const openRosterEnrollFromDetail = () => {
  const course = detailCourse.value
  courseDetailVisible.value = false
  if (course?.id) {
    openRosterEnrollDialog(course)
  }
}

const submitRosterEnrollAllFromClass = async () => {
  const course = rosterEnrollCourse.value
  if (!course?.id || !rosterLinkOptions.value.length) {
    return
  }
  rosterEnrollSubmitting.value = true
  try {
    const result = await api.courses.syncEnrollments(course.id)
    ElMessage.success(
      result?.created > 0
        ? `已将本班花名册全部对齐到选课，新增 ${result.created} 人`
        : '选课名单已与花名册一致'
    )
    rosterEnrollVisible.value = false
    await loadCourses()
  } catch (error) {
    console.error('全班进课失败', error)
  } finally {
    rosterEnrollSubmitting.value = false
  }
}

const submitRosterEnroll = async () => {
  const course = rosterEnrollCourse.value
  if (!course?.id || !rosterEnrollSelection.value.length) {
    return
  }

  const ids = rosterEnrollSelection.value.map(r => r.id).filter(Boolean)
  if (!ids.length) {
    return
  }

  rosterEnrollSubmitting.value = true
  try {
    const result = await api.courses.rosterEnroll(course.id, { student_ids: ids })
    const parts = []
    if (result?.created > 0) {
      parts.push(`新增选课 ${result.created} 人`)
    }
    if (result?.skipped_already_enrolled > 0) {
      parts.push(`已在课 ${result.skipped_already_enrolled} 人`)
    }
    if (result?.skipped_not_in_class_roster > 0) {
      parts.push(`非本班花名册 ${result.skipped_not_in_class_roster} 人`)
    }
    if (result?.skipped_not_found > 0) {
      parts.push(`无效学号 ${result.skipped_not_found} 条`)
    }
    ElMessage.success(parts.length ? parts.join('；') : '未产生变更')
    rosterEnrollVisible.value = false
    await loadCourses()
  } catch (error) {
    console.error('从花名册进课失败', error)
  } finally {
    rosterEnrollSubmitting.value = false
  }
}

const loadOptions = async () => {
  if (isClassTeacherView.value) {
    return
  }

  const [classData, userData, semesterData] = await Promise.all([
    api.classes.list(),
    api.users.list(),
    api.semesters.list()
  ])
  classes.value = classData || []
  teachers.value = (userData || []).filter(item => ['teacher', 'class_teacher'].includes(item.role))
  semesters.value = semesterData || []
}

const addCourseTime = () => {
  form.course_times.push(createEmptyCourseTime())
  formRef.value?.clearValidate('course_times')
}

const removeCourseTime = index => {
  if (form.course_times.length <= 1) {
    return
  }

  form.course_times.splice(index, 1)
  formRef.value?.clearValidate('course_times')
}

const openCreateDialog = () => {
  editingCourse.value = null
  resetForm()
  dialogVisible.value = true
}

const openEditDialog = course => {
  editingCourse.value = course
  revokeLocalCoverPreview()
  pendingCoverFile.value = null
  coverOriginalUrl.value = course.cover_image_url || ''
  if (coverFileInputRef.value) {
    coverFileInputRef.value.value = ''
  }
  const normalizedCourseTimes = normalizeEditableCourseTimes(course)
  const links =
    Array.isArray(course.class_links) && course.class_links.length
      ? course.class_links.map(l => ({
          class_id: l.class_id,
          enrollment_mode: l.enrollment_mode || 'all_in_class'
        }))
      : course.class_id
        ? [{ class_id: course.class_id, enrollment_mode: 'all_in_class' }]
        : [createEmptyClassLink()]

  Object.assign(form, {
    name: course.name,
    class_links: links,
    teacher_id: course.teacher_id,
    semester_id: course.semester_id ?? null,
    course_type: course.course_type || 'required',
    status: course.status || 'active',
    course_times: normalizedCourseTimes.length ? normalizedCourseTimes : [createEmptyCourseTime()],
    description: course.description || ''
  })
  dialogVisible.value = true
}

const triggerCoverPick = () => {
  coverFileInputRef.value?.click()
}

const onCoverFileChange = async e => {
  const input = e.target
  const file = input?.files?.[0]
  if (!file) return
  const maxBytes = 10 * 1024 * 1024
  if (file.size > maxBytes) {
    ElMessage.error('封面图片须不超过 10MB')
    input.value = ''
    return
  }
  if (editingCourse.value?.id) {
    try {
      const res = await api.courses.uploadCoverImage(editingCourse.value.id, file)
      coverOriginalUrl.value = res?.attachment_url || ''
      revokeLocalCoverPreview()
      pendingCoverFile.value = null
      ElMessage.success('封面已更新')
      await loadCourses()
      const updated = (courses.value || []).find(c => String(c.id) === String(editingCourse.value.id))
      if (updated) {
        editingCourse.value = updated
      }
    } catch (err) {
      console.error(err)
    } finally {
      input.value = ''
    }
    return
  }
  revokeLocalCoverPreview()
  pendingCoverFile.value = file
  localCoverPreviewUrl.value = URL.createObjectURL(file)
  input.value = ''
}

const clearCover = async () => {
  if (pendingCoverFile.value) {
    revokeLocalCoverPreview()
    pendingCoverFile.value = null
    if (coverFileInputRef.value) {
      coverFileInputRef.value.value = ''
    }
    return
  }
  if (editingCourse.value?.id && coverOriginalUrl.value) {
    try {
      await api.courses.update(editingCourse.value.id, { remove_cover_image: true })
      coverOriginalUrl.value = ''
      ElMessage.success('已移除课程封面')
      await loadCourses()
      const updated = (courses.value || []).find(c => String(c.id) === String(editingCourse.value.id))
      if (updated) {
        editingCourse.value = updated
      }
    } catch (e) {
      console.error(e)
    }
  }
}

const getCourseTimeLines = course =>
  normalizeEditableCourseTimes(course)
    .map(formatCourseTimeEntry)
    .filter(Boolean)

const submitForm = async () => {
  await formRef.value.validate()
  submitting.value = true

  try {
    const payload = {
      name: form.name,
      teacher_id: form.teacher_id,
      semester_id: form.semester_id || null,
      course_type: form.course_type,
      status: form.status,
      course_times: serializeCourseTimesPayload(form.course_times),
      description: form.description
    }
    if (form.course_type === 'required') {
      payload.class_links = form.class_links.map(r => ({
        class_id: r.class_id,
        enrollment_mode: r.enrollment_mode || 'all_in_class'
      }))
    } else {
      payload.class_id = null
    }

    if (editingCourse.value) {
      await api.courses.update(editingCourse.value.id, payload)
      ElMessage.success('课程已更新')
    } else {
      const created = await api.courses.create(payload)
      ElMessage.success('课程已创建')
      if (pendingCoverFile.value && created?.id) {
        try {
          await api.courses.uploadCoverImage(created.id, pendingCoverFile.value)
        } catch (err) {
          console.error(err)
          ElMessage.warning('课程已创建，但封面上传失败，可在编辑中重试。')
        }
      }
    }

    revokeLocalCoverPreview()
    pendingCoverFile.value = null

    dialogVisible.value = false
    await loadCourses()
  } finally {
    submitting.value = false
  }
}

const resetLlmForm = () => {
  llmQuotaUsage.value = null
  Object.assign(llmForm, {
    is_enabled: false,
    response_language: '',
    max_input_tokens: 16000,
    max_output_tokens: null,
    system_prompt: '',
    teacher_prompt: '',
    endpoints: [],
    groups: []
  })
}

const applyLlmConfig = config => {
  resetLlmForm()
  if (!config) {
    return
  }
  llmVisualValidationNotice.value = config.visual_validation_notice || llmVisualValidationNotice.value
  llmForm.is_enabled = Boolean(config.is_enabled)
  llmForm.response_language = config.response_language || ''
  llmForm.max_input_tokens = config.max_input_tokens ?? 16000
  llmForm.max_output_tokens = config.max_output_tokens ?? null
  llmForm.system_prompt = config.system_prompt || ''
  llmForm.teacher_prompt = config.teacher_prompt || ''
  llmForm.endpoints = (config.endpoints || []).map(item => ({
    preset_id: item.preset_id,
    priority: item.priority
  }))
  llmForm.groups = (config.groups || []).map(g => ({
    name: g.name || '',
    priority: g.priority,
    members: (g.members || []).map(m => ({ preset_id: m.preset_id, priority: m.priority }))
  }))
  llmQuotaUsage.value = config.quota_usage || null
}

const openLlmConfigDialog = async course => {
  llmDialogCourse.value = course
  llmDialogVisible.value = true
  llmLoading.value = true
  try {
    const [presets, config] = await Promise.all([
      api.llmSettings.listPresets(),
      api.llmSettings.getCourseConfig(course.id)
    ])
    llmPresets.value = presets || []
    applyLlmConfig(config)
  } finally {
    llmLoading.value = false
  }
}

const isPresetSelected = presetId =>
  llmForm.endpoints.some(item => String(item.preset_id) === String(presetId))

const getPresetPriority = presetId =>
  llmForm.endpoints.find(item => String(item.preset_id) === String(presetId))?.priority || 1

const togglePresetSelection = (preset, checked) => {
  const existingIndex = llmForm.endpoints.findIndex(item => String(item.preset_id) === String(preset.id))
  if (!checked && existingIndex >= 0) {
    llmForm.endpoints.splice(existingIndex, 1)
    return
  }
  if (checked && existingIndex < 0) {
    llmForm.endpoints.push({
      preset_id: preset.id,
      priority: llmForm.endpoints.length + 1
    })
  }
}

const updatePresetPriority = (presetId, value) => {
  const target = llmForm.endpoints.find(item => String(item.preset_id) === String(presetId))
  if (!target) {
    return
  }
  target.priority = value || 1
}

const saveLlmConfig = async () => {
  if (!llmDialogCourse.value) {
    return
  }
  llmSaving.value = true
  try {
    const hasGroupRouting = Array.isArray(llmForm.groups) && llmForm.groups.length > 0
    const groupPayload = hasGroupRouting
      ? llmForm.groups.map((g, idx) => ({
        priority: g.priority != null ? g.priority : idx + 1,
        name: (g.name || '').trim() || `group ${idx + 1}`,
        members: (g.members || [])
          .map((m, mj) => ({ preset_id: m.preset_id, priority: m.priority != null ? m.priority : mj + 1 }))
          .sort((a, b) => a.priority - b.priority)
      }))
      : null
    await api.llmSettings.updateCourseConfig(llmDialogCourse.value.id, {
      is_enabled: llmForm.is_enabled,
      response_language: llmForm.response_language?.trim() || null,
      max_input_tokens: llmForm.max_input_tokens,
      max_output_tokens: normalizeNullableNumber(llmForm.max_output_tokens),
      system_prompt: llmForm.system_prompt?.trim() || null,
      teacher_prompt: llmForm.teacher_prompt?.trim() || null,
      ...(
        hasGroupRouting
          ? { groups: groupPayload, endpoints: [] }
          : { endpoints: [...llmForm.endpoints].sort((left, right) => left.priority - right.priority) }
      ),
      replace_group_routing_with_flat_endpoints: hasGroupRouting ? false : true
    })
    ElMessage.success('LLM 配置已保存')
    llmDialogVisible.value = false
  } finally {
    llmSaving.value = false
  }
}

const deleteCourse = async course => {
  try {
    await ElMessageBox.confirm(`确认删除课程“${course.name}”吗？`, '删除课程', { type: 'warning' })
    await api.courses.delete(course.id)
    ElMessage.success('课程已删除')
    await loadCourses()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除课程失败', error)
      ElMessage.error(error?.response?.data?.detail || error?.message || '删除课程失败')
    }
  }
}

const normalizeExamTypeKey = examType => `${examType || ''}`.trim().toLowerCase()

const average = values => {
  if (!values.length) {
    return null
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

const buildFinalScoreMap = (scores, weights) => {
  const scoreMap = new Map()
  const weightMap = new Map(
    (weights || []).map(item => [normalizeExamTypeKey(item.exam_type), Number(item.weight || 0)])
  )

  ;(scores || []).forEach(score => {
    const studentId = Number(score.student_id)
    const examTypeKey = normalizeExamTypeKey(score.exam_type)
    const numericScore = Number(score.score)

    if (!scoreMap.has(studentId)) {
      scoreMap.set(studentId, new Map())
    }

    if (!scoreMap.get(studentId).has(examTypeKey)) {
      scoreMap.get(studentId).set(examTypeKey, [])
    }

    scoreMap.get(studentId).get(examTypeKey).push(numericScore)
  })

  const finalScoreMap = new Map()

  scoreMap.forEach((examMap, studentId) => {
    let weightedTotal = 0
    const allScores = []

    examMap.forEach((values, examTypeKey) => {
      const examAverage = average(values)
      allScores.push(...values)

      const weight = weightMap.get(examTypeKey)
      if (weight && examAverage !== null) {
        weightedTotal += (examAverage * weight) / 100
      }
    })

    let finalScore = null

    if (weightMap.size > 0) {
      finalScore = weightedTotal
    } else {
      finalScore = average(allScores)
    }

    finalScoreMap.set(studentId, finalScore)
  })

  return finalScoreMap
}

const formatFinalScore = value => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '暂无'
  }

  const numeric = Number(value)
  return Number.isInteger(numeric) ? `${numeric}` : numeric.toFixed(1)
}

const openCourseDetail = async course => {
  detailCourse.value = course
  courseDetailVisible.value = true
  courseDetailLoading.value = true

  const ctxClassId =
    course.class_id || (Array.isArray(course.class_links) && course.class_links[0]?.class_id) || null

  try {
    const [studentsResult, attendanceResult, scoresResult, weightResult, homeworkRows] = await Promise.all([
      api.courses.getStudents(course.id),
      api.attendance.list({
        class_id: ctxClassId,
        subject_id: course.id,
        page: 1,
        page_size: 1000
      }),
      api.scores.list({
        class_id: ctxClassId,
        subject_id: course.id,
        page: 1,
        page_size: 1000
      }),
      api.scores.getWeights(course.id).catch(() => []),
      loadAllPages(params =>
        api.homework.list({
          ...params,
          class_id: ctxClassId,
          subject_id: course.id
        })
      )
    ])

    const submissionResults = await Promise.all(
      homeworkRows.map(homework => api.homework.getSubmissions(homework.id))
    )

    const absenceCountMap = new Map()
    ;(attendanceResult?.data || []).forEach(item => {
      if (item.status === 'absent') {
        const studentId = Number(item.student_id)
        absenceCountMap.set(studentId, (absenceCountMap.get(studentId) || 0) + 1)
      }
    })

    const missingHomeworkMap = new Map()
    submissionResults.forEach(result => {
      ;(result?.data || []).forEach(item => {
        if (item.status !== 'submitted') {
          const studentId = Number(item.student_id)
          missingHomeworkMap.set(studentId, (missingHomeworkMap.get(studentId) || 0) + 1)
        }
      })
    })

    const finalScoreMap = buildFinalScoreMap(scoresResult?.data || [], weightResult || [])

    courseDetailRows.value = (studentsResult || []).map(student => ({
      student_id: student.student_id,
      student_name: student.student_name,
      student_no: student.student_no,
      absence_count: absenceCountMap.get(Number(student.student_id)) || 0,
      missing_homework_count: missingHomeworkMap.get(Number(student.student_id)) || 0,
      final_score_text: formatFinalScore(finalScoreMap.get(Number(student.student_id)))
    }))
  } finally {
    courseDetailLoading.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadCourses(), loadOptions()])
})

watch(rosterPickClassId, async () => {
  if (!rosterEnrollVisible.value) {
    return
  }
  await loadRosterRowsForPick()
})

watch(
  () => userStore.userInfo?.id,
  async () => {
    await Promise.all([loadCourses(), loadOptions()])
  }
)
</script>

<style scoped>
.courses-page {
  padding: 24px;
  min-width: 0;
  overflow-x: hidden;
  width: min(100%, 1180px);
  margin: 0 auto;
}

.courses-page :deep(.el-card) {
  min-width: 0;
  border-radius: var(--wa-radius-lg);
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 86%, transparent);
  box-shadow: var(--wa-shadow-surface);
}

.courses-page :deep(.el-card__body) {
  overflow-x: hidden;
}

.courses-table-scroll,
.courses-detail-scroll,
.courses-roster-scroll {
  overflow-x: auto;
  max-width: 100%;
}

.courses-table-scroll :deep(.el-table) {
  min-width: 1260px;
}

.courses-detail-scroll :deep(.el-table) {
  min-width: 760px;
}

.courses-roster-scroll :deep(.el-table) {
  min-width: 520px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}

.page-title {
  margin: 0 0 8px;
  font-size: 28px;
  color: var(--wa-color-text);
}

.page-subtitle {
  margin: 0;
  color: var(--wa-color-text-muted);
  line-height: 1.6;
}

.course-detail-meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 18px;
  color: #334155;
}

.course-detail-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.course-time-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.course-time-line {
  line-height: 1.6;
  color: #334155;
}

.course-times-editor {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 16px;
}

.course-times-editor__add {
  align-self: flex-start;
}

.llm-notice {
  margin-bottom: 18px;
}

.llm-endpoints {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 12px;
}

.llm-endpoint-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  border: 1px solid #dbe4f0;
  border-radius: 14px;
  background: #f8fbff;
}

.llm-endpoint-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.llm-group-list {
  margin: 8px 0 0 16px;
  padding: 0;
  list-style: disc;
}
.llm-group-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.llm-validate-pills {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #64748b;
}

.llm-validate-detail {
  line-height: 1.45;
  max-width: 100%;
  word-break: break-word;
}

.course-time-panel {
  border: 1px solid #dbe4f0;
  border-radius: 18px;
  background: #f8fbff;
  padding: 18px;
}

.course-time-panel__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.course-time-panel__title {
  font-size: 16px;
  font-weight: 600;
  color: #0f172a;
}

.course-time-panel__subtitle {
  margin-top: 6px;
  font-size: 13px;
  color: #64748b;
}

.course-time-panel__fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.course-time-panel__fields :deep(.el-form-item) {
  margin-bottom: 0;
}

.course-time-panel__schedule {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.course-time-panel__schedule-label {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

@media (max-width: 900px) {
  .courses-page {
    padding: 18px 14px;
  }

  .course-detail-meta,
  .page-header,
  .course-time-panel__header {
    grid-template-columns: 1fr;
    flex-direction: column;
  }

  .course-time-panel__fields {
    grid-template-columns: 1fr;
  }
}

.roster-enroll-alert {
  margin-bottom: 16px;
}

.roster-enroll-alert-body {
  margin: 0;
  line-height: 1.65;
  color: #334155;
}

.roster-enroll-meta {
  margin-bottom: 12px;
  color: #475569;
  font-size: 14px;
}

.cover-field {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-start;
}

.cover-preview {
  width: 160px;
  height: 100px;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  overflow: hidden;
  flex-shrink: 0;
  background: #f8fafc;
}

.cover-preview--empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-size: 13px;
}

.cover-actions {
  flex: 1;
  min-width: 200px;
}

.cover-file-input {
  display: none;
}

.cover-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
}

.subject-elective-hint {
  margin-bottom: 12px;
}

.class-links-editor {
  display: grid;
  gap: 10px;
  width: 100%;
}

.class-link-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.class-link-mode {
  flex: 1;
  min-width: 240px;
}

.class-links-editor__add {
  justify-self: start;
}

.roster-enroll-pick-class {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
</style>
