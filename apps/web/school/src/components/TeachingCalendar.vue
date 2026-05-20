<template>
  <div class="teaching-calendar">
    <div class="calendar-header">
      <div class="calendar-header__info">
        <div class="calendar-title-row">
          <h3>教学日历</h3>
          <span class="calendar-range">{{ courseRangeLabel }}</span>
        </div>
        <div v-if="scheduleLabel" class="calendar-schedule">
          上课时间：{{ scheduleLabel }}
        </div>
      </div>
      <div class="calendar-actions">
        <button type="button" class="calendar-nav" @click="goToPreviousMonth">上个月</button>
        <div class="calendar-month">{{ currentMonthLabel }}</div>
        <button type="button" class="calendar-nav" @click="goToNextMonth">下个月</button>
      </div>
    </div>

    <div class="calendar-legend">
      <span class="legend-item">
        <i class="legend-dot legend-dot-class"></i>
        上课日
      </span>
      <span class="legend-item">
        <i class="legend-dot legend-dot-holiday"></i>
        法定假期
      </span>
    </div>

    <el-alert
      v-if="hasUnsupportedSchedule"
      type="warning"
      :closable="false"
      class="calendar-alert"
    >
      当前课程存在无法识别的每周时间格式，请先在课程管理里重新选择结构化课程时间后再查看教学日历。
    </el-alert>

    <el-empty
      v-else-if="!hasRenderableCalendar"
      description="请先完善课程时间中的起始日期、结束日期和每周时间。"
    />

    <template v-else>
      <div class="calendar-summary">
        <span>本月上课 {{ visibleMonthStats.classDays }} 天</span>
        <span>本月假期 {{ visibleMonthStats.holidayDays }} 天</span>
      </div>

      <div class="calendar-grid">
        <div
          v-for="weekday in weekdayLabels"
          :key="weekday"
          class="calendar-weekday"
        >
          {{ weekday }}
        </div>

        <div
          v-for="cell in calendarCells"
          :key="cell.dateKey"
          class="calendar-cell"
          :class="{
            'is-outside': !cell.isCurrentMonth,
            'is-holiday': Boolean(cell.holiday),
            'is-class-day': Boolean(cell.classDay),
            'is-selected': selectedDate && cell.dateKey === selectedDate
          }"
          role="button"
          :tabindex="cell.classDay ? 0 : -1"
          @click="handleCellClick(cell)"
          @keydown.enter.prevent="handleCellClick(cell)"
        >
          <div class="calendar-cell__day">{{ cell.dayNumber }}</div>
          <div v-if="cell.holiday" class="calendar-pill calendar-pill-holiday">
            {{ cell.holiday.name }}
          </div>
          <div v-else-if="cell.classDay" class="calendar-pill calendar-pill-class">
            上课
          </div>
          <div v-if="cell.classDay" class="calendar-note">
            {{ cell.classDay.summary }}
          </div>
          <div
            v-else-if="cell.holiday?.suspendsClass"
            class="calendar-note calendar-note-muted"
          >
            停课
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

import { parseScheduleValue } from '@/utils/courseSchedule'
import {
  formatCourseTimeEntry,
  formatCourseTimeDateRange,
  getCourseTimeDateBounds,
  normalizeCourseBoundaryDate,
  resolveCourseTimes
} from '@/utils/courseTimes'
import { buildHolidayMap } from '@/utils/holidayCalendar'

const props = defineProps({
  course: {
    type: Object,
    default: null
  },
  selectedDate: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['select-date'])

const ONE_DAY_MS = 24 * 60 * 60 * 1000
const weekdayLabels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const legacyWeekdayPatterns = [
  { value: 1, patterns: [/周一/, /星期一/, /每周一/] },
  { value: 2, patterns: [/周二/, /星期二/, /每周二/] },
  { value: 3, patterns: [/周三/, /星期三/, /每周三/] },
  { value: 4, patterns: [/周四/, /星期四/, /每周四/] },
  { value: 5, patterns: [/周五/, /星期五/, /每周五/] },
  { value: 6, patterns: [/周六/, /星期六/, /每周六/] },
  { value: 7, patterns: [/周日/, /星期日/, /星期天/, /周天/, /每周日/, /每周天/] }
]

const currentMonth = ref(new Date())

const toDateKey = date => {
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

const addDays = (date, days) => new Date(date.getTime() + days * ONE_DAY_MS)

const normalizePeriods = periods => [...new Set(periods)].sort((left, right) => left - right)

const formatCompactPeriodSummary = periods => {
  const sortedPeriods = normalizePeriods(periods)

  if (!sortedPeriods.length) {
    return '常规授课'
  }

  const groups = []
  let start = sortedPeriods[0]
  let end = sortedPeriods[0]

  for (const period of sortedPeriods.slice(1)) {
    if (period === end + 1) {
      end = period
      continue
    }

    groups.push(start === end ? `${start}节` : `${start}-${end}节`)
    start = period
    end = period
  }

  groups.push(start === end ? `${start}节` : `${start}-${end}节`)
  return groups.join('、')
}

const extractLegacyWeekdays = scheduleText => {
  const normalizedText = `${scheduleText || ''}`.trim()

  if (!normalizedText) {
    return []
  }

  return legacyWeekdayPatterns.filter(day =>
    day.patterns.some(pattern => pattern.test(normalizedText))
  )
}

const buildScheduleByDay = scheduleText => {
  const parsedSlots = parseScheduleValue(scheduleText)

  if (parsedSlots.length) {
    return parsedSlots.reduce((map, slot) => {
      const [dayValueRaw, periodValueRaw] = slot.split('-')
      const dayValue = Number(dayValueRaw)
      const periodValue = Number(periodValueRaw)

      if (!map.has(dayValue)) {
        map.set(dayValue, [])
      }

      map.get(dayValue).push(periodValue)
      return map
    }, new Map())
  }

  return extractLegacyWeekdays(scheduleText).reduce((map, day) => {
    map.set(day.value, [])
    return map
  }, new Map())
}

const courseTimeEntries = computed(() =>
  resolveCourseTimes(props.course).map(item => ({
    ...item,
    startDate: normalizeCourseBoundaryDate(item.course_start_at),
    endDate: normalizeCourseBoundaryDate(item.course_end_at),
    scheduleByDay: buildScheduleByDay(item.weekly_schedule)
  }))
)

const validCourseTimeEntries = computed(() =>
  courseTimeEntries.value.filter(item =>
    item.startDate && item.endDate && item.endDate >= item.startDate && item.scheduleByDay.size > 0
  )
)

const hasUnsupportedSchedule = computed(() =>
  courseTimeEntries.value.some(item => Boolean(item.weekly_schedule) && item.scheduleByDay.size === 0)
)

const hasRenderableCalendar = computed(() =>
  validCourseTimeEntries.value.length > 0 && !hasUnsupportedSchedule.value
)

const courseDateBounds = computed(() => getCourseTimeDateBounds(props.course))

const holidayMap = computed(() =>
  courseDateBounds.value.startDate && courseDateBounds.value.endDate
    ? buildHolidayMap(courseDateBounds.value.startDate, courseDateBounds.value.endDate)
    : {}
)

const classDateMap = computed(() => {
  if (!hasRenderableCalendar.value) {
    return {}
  }

  const entries = {}

  for (const courseTime of validCourseTimeEntries.value) {
    let currentDateValue = new Date(courseTime.startDate)

    while (currentDateValue <= courseTime.endDate) {
      const dayValue = currentDateValue.getDay() === 0 ? 7 : currentDateValue.getDay()
      const periods = courseTime.scheduleByDay.get(dayValue) || []
      const dateKey = toDateKey(currentDateValue)

      if (courseTime.scheduleByDay.has(dayValue) && !holidayMap.value[dateKey]) {
        const mergedPeriods = normalizePeriods([
          ...(entries[dateKey]?.periods || []),
          ...periods
        ])

        entries[dateKey] = {
          periods: mergedPeriods,
          summary: formatCompactPeriodSummary(mergedPeriods)
        }
      }

      currentDateValue = addDays(currentDateValue, 1)
    }
  }

  return entries
})

const resolveDateMeta = date => {
  const normalizedDate = normalizeCourseBoundaryDate(date)

  if (!normalizedDate) {
    return { dateKey: '', holiday: null, classDay: null }
  }

  const dateKey = toDateKey(normalizedDate)
  const dayValue = normalizedDate.getDay() === 0 ? 7 : normalizedDate.getDay()
  const holiday = holidayMap.value[dateKey]
    ? {
        ...holidayMap.value[dateKey],
        suspendsClass: validCourseTimeEntries.value.some(item => item.scheduleByDay.has(dayValue))
      }
    : null

  return {
    dateKey,
    holiday,
    classDay: classDateMap.value[dateKey] || null
  }
}

const currentMonthLabel = computed(() =>
  `${currentMonth.value.getFullYear()}年${currentMonth.value.getMonth() + 1}月`
)

const scheduleLabel = computed(() =>
  validCourseTimeEntries.value
    .map(formatCourseTimeEntry)
    .filter(Boolean)
    .join('；')
)

const courseRangeLabel = computed(() => {
  if (!validCourseTimeEntries.value.length) {
    return '未设置教学周期'
  }

  return validCourseTimeEntries.value
    .map(item => formatCourseTimeDateRange(item.startDate, item.endDate))
    .filter(Boolean)
    .join('；')
})

const calendarCells = computed(() => {
  const firstDayOfMonth = new Date(currentMonth.value.getFullYear(), currentMonth.value.getMonth(), 1)
  const startOffset = (firstDayOfMonth.getDay() + 6) % 7
  const calendarStartDate = addDays(firstDayOfMonth, -startOffset)

  return Array.from({ length: 42 }, (_, index) => {
    const date = addDays(calendarStartDate, index)
    const { dateKey, holiday, classDay } = resolveDateMeta(date)

    return {
      date,
      dateKey,
      dayNumber: date.getDate(),
      isCurrentMonth: date.getMonth() === currentMonth.value.getMonth(),
      holiday,
      classDay
    }
  })
})

const visibleMonthStats = computed(() => {
  const targetYear = currentMonth.value.getFullYear()
  const targetMonth = currentMonth.value.getMonth()

  const isCurrentMonthDateKey = dateKey => {
    const date = normalizeCourseBoundaryDate(dateKey)
    return date && date.getFullYear() === targetYear && date.getMonth() === targetMonth
  }

  return {
    classDays: Object.keys(classDateMap.value).filter(isCurrentMonthDateKey).length,
    holidayDays: Object.keys(holidayMap.value).filter(isCurrentMonthDateKey).length
  }
})

const resolveInitialMonth = course => {
  const bounds = getCourseTimeDateBounds(course)
  const today = normalizeCourseBoundaryDate(new Date())

  if (bounds.startDate && bounds.endDate && today >= bounds.startDate && today <= bounds.endDate) {
    return today
  }

  return bounds.startDate || today || new Date()
}

const goToPreviousMonth = () => {
  currentMonth.value = new Date(currentMonth.value.getFullYear(), currentMonth.value.getMonth() - 1, 1)
}

const goToNextMonth = () => {
  currentMonth.value = new Date(currentMonth.value.getFullYear(), currentMonth.value.getMonth() + 1, 1)
}

const handleCellClick = cell => {
  if (!cell?.classDay) return
  emit('select-date', cell.dateKey)
}

watch(
  () => props.course,
  course => {
    currentMonth.value = resolveInitialMonth(course)
  },
  { immediate: true }
)
</script>

<style scoped>
.teaching-calendar {
  width: 100%;
}

.calendar-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 12px;
}

.calendar-header__info {
  min-width: 0;
}

.calendar-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.calendar-title-row h3 {
  margin: 0;
  font-size: 20px;
  color: #0f172a;
}

.calendar-range,
.calendar-schedule,
.calendar-summary {
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.calendar-schedule {
  margin-top: 4px;
}

.calendar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.calendar-nav {
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #334155;
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
}

.calendar-nav:hover {
  border-color: #93c5fd;
  color: #1d4ed8;
}

.calendar-month {
  min-width: 90px;
  text-align: center;
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.calendar-legend,
.calendar-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
}

.calendar-legend {
  margin-bottom: 12px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #64748b;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
}

.legend-dot-class {
  background: #2563eb;
}

.legend-dot-holiday {
  background: #ef4444;
}

.calendar-alert {
  margin-bottom: 12px;
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  border: 1px solid #dbe4f0;
  border-radius: 18px;
  overflow: hidden;
}

.calendar-weekday {
  padding: 10px 6px;
  text-align: center;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  background: #f8fafc;
  border-bottom: 1px solid #dbe4f0;
}

.calendar-cell {
  min-height: 72px;
  padding: 6px;
  border-right: 1px solid #dbe4f0;
  border-bottom: 1px solid #dbe4f0;
  background: #fff;
}

.calendar-cell:nth-child(7n) {
  border-right: none;
}

.calendar-cell.is-outside {
  background: #f8fafc;
}

.calendar-cell.is-class-day {
  background: linear-gradient(180deg, #eff6ff 0%, #dbeafe 100%);
  cursor: pointer;
}

.calendar-cell.is-class-day:hover,
.calendar-cell.is-selected {
  outline: 2px solid #2563eb;
  outline-offset: -2px;
}

.calendar-cell.is-holiday {
  background: linear-gradient(180deg, #fff1f2 0%, #ffe4e6 100%);
}

.calendar-cell__day {
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
}

.calendar-pill {
  display: inline-flex;
  align-items: center;
  margin-top: 6px;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.calendar-pill-class {
  color: #1d4ed8;
  background: rgba(37, 99, 235, 0.12);
}

.calendar-pill-holiday {
  color: #b91c1c;
  background: rgba(239, 68, 68, 0.14);
}

.calendar-note {
  margin-top: 6px;
  font-size: 11px;
  line-height: 1.5;
  color: #334155;
}

.calendar-note-muted {
  color: #991b1b;
}

@media (max-width: 900px) {
  .calendar-header {
    flex-direction: column;
  }

  .calendar-actions {
    width: 100%;
    justify-content: space-between;
  }

  .calendar-cell {
    min-height: 68px;
  }
}
</style>
