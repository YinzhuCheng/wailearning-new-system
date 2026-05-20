<template>
  <div class="semester-calendar">
    <div class="calendar-header">
      <div>
        <h3>学期日历</h3>
        <p>{{ headerText }}</p>
      </div>
      <div class="calendar-legend">
        <span v-for="item in legendCourses" :key="item.id" class="legend-item">
          <i class="legend-dot" :style="{ background: item.color }"></i>
          {{ item.name }}
        </span>
      </div>
    </div>

    <el-empty
      v-if="!hasScheduleBlocks"
      description="当前班级还没有可展示的课程时间安排。"
    />

    <div v-else class="schedule-wrapper">
      <table class="schedule-table">
        <thead>
          <tr>
            <th class="section-column">节次/星期</th>
            <th class="time-column">课程/小时时间</th>
            <th v-for="day in weekdayColumns" :key="day.value">
              {{ day.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in tableRows" :key="row.period.value">
            <td
              v-if="row.sectionRowspan"
              class="section-cell"
              :rowspan="row.sectionRowspan"
            >
              <div class="section-cell__title">{{ row.sectionTitle }}</div>
              <div class="section-cell__time">{{ row.sectionTime }}</div>
            </td>

            <td class="time-cell">
              <div class="time-cell__time">{{ row.period.time }}</div>
              <div class="time-cell__label">{{ row.period.label }}</div>
            </td>

            <template v-for="cell in row.cells" :key="`${row.period.value}-${cell.dayValue}`">
              <td
                v-if="!cell.skip"
                class="course-cell"
                :rowspan="cell.block?.rowSpan || 1"
              >
                <div
                  v-if="cell.block"
                  class="course-card"
                  :style="{ background: cell.block.color }"
                >
                  <strong>{{ cell.block.courseName }}</strong>
                  <span>{{ cell.block.teacherName }}</span>
                  <small>{{ cell.block.dateRange }}</small>
                </div>
              </td>
            </template>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

import { PERIOD_OPTIONS, parseScheduleSlotKey, parseScheduleValue } from '@/utils/courseSchedule'
import { formatCourseTimeCardDateRange, resolveCourseTimes } from '@/utils/courseTimes'

const props = defineProps({
  className: {
    type: String,
    default: ''
  },
  courses: {
    type: Array,
    default: () => []
  }
})

const weekdayColumns = [
  { value: 1, label: '星期一' },
  { value: 2, label: '星期二' },
  { value: 3, label: '星期三' },
  { value: 4, label: '星期四' },
  { value: 5, label: '星期五' }
]

const sectionGroups = [
  { title: '第一大节次(1-2节)', time: '08:00-09:30', periods: [1, 2] },
  { title: '第二大节次(3-4节)', time: '10:00-11:30', periods: [3, 4] },
  { title: '第三大节次(5-6节)', time: '12:00-13:30', periods: [5, 6] },
  { title: '第四大节次(7-8节)', time: '14:00-15:30', periods: [7, 8] },
  { title: '第五大节次(9-10节)', time: '16:00-17:30', periods: [9, 10] },
  { title: '第六大节次(11-12节)', time: '18:00-19:30', periods: [11, 12] },
  { title: '第七大节次(13-14节)', time: '19:40-21:10', periods: [13, 14] }
]

const palette = [
  '#dbeafe',
  '#fee2e2',
  '#fef3c7',
  '#dcfce7',
  '#ede9fe',
  '#fde68a',
  '#e0f2fe',
  '#fce7f3'
]

const periodRows = PERIOD_OPTIONS.filter(item => item.value <= 14)

const buildPeriodGroups = weeklySchedule => {
  const slots = parseScheduleValue(weeklySchedule)
  const groupedByDay = new Map()

  for (const slot of slots) {
    const parsed = parseScheduleSlotKey(slot)
    if (!parsed || parsed.dayValue > 5) {
      continue
    }

    if (!groupedByDay.has(parsed.dayValue)) {
      groupedByDay.set(parsed.dayValue, [])
    }

    groupedByDay.get(parsed.dayValue).push(parsed.periodValue)
  }

  return [...groupedByDay.entries()].flatMap(([dayValue, periods]) => {
    const sortedPeriods = [...new Set(periods)].sort((left, right) => left - right)
    const groups = []
    let start = sortedPeriods[0]
    let end = sortedPeriods[0]

    for (const period of sortedPeriods.slice(1)) {
      if (period === end + 1) {
        end = period
        continue
      }

      groups.push({ dayValue, start, end })
      start = period
      end = period
    }

    groups.push({ dayValue, start, end })
    return groups
  })
}

const normalizedCourses = computed(() =>
  (props.courses || []).map((course, index) => ({
    ...course,
    color: palette[index % palette.length]
  }))
)

const hasScheduleBlocks = computed(() =>
  normalizedCourses.value.some(course => resolveCourseTimes(course).length > 0)
)

const legendCourses = computed(() =>
  normalizedCourses.value.map(course => ({
    id: course.id,
    name: course.name,
    color: course.color
  }))
)

const headerText = computed(() => {
  if (props.className) {
    return `${props.className} 每周课程安排`
  }

  return '按班级展示每周课程安排'
})

const blockMap = computed(() => {
  const map = new Map()

  normalizedCourses.value.forEach(course => {
    resolveCourseTimes(course).forEach(courseTime => {
      buildPeriodGroups(courseTime.weekly_schedule).forEach(group => {
        const key = `${group.start}-${group.dayValue}`
        map.set(key, {
          courseName: course.name,
          teacherName: course.teacher_name || '未安排教师',
          dateRange: formatCourseTimeCardDateRange(courseTime.course_start_at, courseTime.course_end_at) || '学期内',
          rowSpan: group.end - group.start + 1,
          color: course.color
        })

        for (let period = group.start + 1; period <= group.end; period += 1) {
          map.set(`${period}-${group.dayValue}`, { skip: true })
        }
      })
    })
  })

  return map
})

const sectionLookup = new Map(
  sectionGroups.flatMap(group =>
    group.periods.map((period, index) => [
      period,
      {
        title: group.title,
        time: group.time,
        rowspan: index === 0 ? group.periods.length : 0
      }
    ])
  )
)

const tableRows = computed(() =>
  periodRows.map(period => {
    const section = sectionLookup.get(period.value)

    return {
      period,
      sectionTitle: section?.title || '',
      sectionTime: section?.time || '',
      sectionRowspan: section?.rowspan || 0,
      cells: weekdayColumns.map(day => ({
        dayValue: day.value,
        ...(blockMap.value.get(`${period.value}-${day.value}`) || { block: null }),
        block: blockMap.value.get(`${period.value}-${day.value}`)?.skip
          ? null
          : blockMap.value.get(`${period.value}-${day.value}`) || null,
        skip: Boolean(blockMap.value.get(`${period.value}-${day.value}`)?.skip)
      }))
    }
  })
)
</script>

<style scoped>
.semester-calendar {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.calendar-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.calendar-header h3 {
  margin: 0 0 8px;
  font-size: 24px;
  color: #0f172a;
}

.calendar-header p {
  margin: 0;
  font-size: 14px;
  color: #64748b;
}

.calendar-legend {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  background: #f8fafc;
  color: #475569;
  font-size: 12px;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
}

.schedule-wrapper {
  overflow-x: auto;
  border: 1px solid #dbe4f0;
  border-radius: 20px;
  background: #fff;
}

.schedule-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 920px;
}

.schedule-table th,
.schedule-table td {
  border: 1px solid #dbe4f0;
}

.schedule-table thead th {
  padding: 14px 10px;
  background: #f8fafc;
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
  text-align: center;
}

.section-column {
  width: 150px;
}

.time-column {
  width: 180px;
}

.section-cell {
  width: 150px;
  padding: 12px 10px;
  font-size: 14px;
  text-align: center;
  background: #f8fafc;
  color: #0f172a;
}

.section-cell__title {
  font-size: 14px;
  font-weight: 700;
  line-height: 1.6;
}

.section-cell__time {
  margin-top: 8px;
  font-size: 14px;
  color: #64748b;
}

.time-cell {
  width: 180px;
  padding: 10px;
  font-size: 14px;
  text-align: center;
  background: #fcfdff;
}

.time-cell__time {
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
}

.time-cell__label {
  margin-top: 6px;
  font-size: 14px;
  color: #64748b;
}

.course-cell {
  min-width: 150px;
  height: 82px;
  padding: 8px;
  font-size: 14px;
  background: #fff;
  vertical-align: top;
}

.course-card {
  display: flex;
  min-height: 100%;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
  border-radius: 16px;
  padding: 12px 10px;
  text-align: center;
  color: #0f172a;
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.2);
}

.course-card strong {
  font-size: 14px;
  line-height: 1.5;
}

.course-card span,
.course-card small {
  font-size: 14px;
  color: #475569;
  line-height: 1.5;
}

@media (max-width: 960px) {
  .calendar-header {
    flex-direction: column;
  }

  .calendar-legend {
    justify-content: flex-start;
  }
}
</style>
