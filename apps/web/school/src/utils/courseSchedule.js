export const WEEK_DAYS = [
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
  { value: 7, label: '周日' }
]

export const PERIOD_OPTIONS = [
  { value: 1, label: '第1小节', time: '08:00-08:45' },
  { value: 2, label: '第2小节', time: '08:45-09:30' },
  { value: 3, label: '第3小节', time: '10:00-10:45' },
  { value: 4, label: '第4小节', time: '10:45-11:30' },
  { value: 5, label: '第5小节', time: '12:00-12:45' },
  { value: 6, label: '第6小节', time: '12:45-13:30' },
  { value: 7, label: '第7小节', time: '14:00-14:45' },
  { value: 8, label: '第8小节', time: '14:45-15:30' },
  { value: 9, label: '第9小节', time: '16:00-16:45' },
  { value: 10, label: '第10小节', time: '16:45-17:30' },
  { value: 11, label: '第11小节', time: '18:00-18:45' },
  { value: 12, label: '第12小节', time: '18:45-19:30' },
  { value: 13, label: '第13小节', time: '19:40-20:25' },
  { value: 14, label: '第14小节', time: '20:25-21:10' }
]

const DAY_MAP = Object.fromEntries(WEEK_DAYS.map(item => [item.value, item]))
const PERIOD_MAP = Object.fromEntries(PERIOD_OPTIONS.map(item => [item.value, item]))
const CANONICAL_SEGMENT_PATTERN = /^([1-7])@(\d{1,2})(,\d{1,2})*$/

export const buildScheduleSlotKey = (dayValue, periodValue) => `${dayValue}-${periodValue}`

export const parseScheduleSlotKey = slotKey => {
  const [dayValue, periodValue] = `${slotKey || ''}`.split('-').map(value => Number(value))

  if (!DAY_MAP[dayValue] || !PERIOD_MAP[periodValue]) {
    return null
  }

  return { dayValue, periodValue }
}

const normalizeSlots = slots => {
  const unique = new Map()

  for (const slot of slots || []) {
    const parsedSlot = parseScheduleSlotKey(slot)

    if (!parsedSlot) {
      continue
    }

    unique.set(buildScheduleSlotKey(parsedSlot.dayValue, parsedSlot.periodValue), true)
  }

  return [...unique.keys()].sort((left, right) => {
    const leftSlot = parseScheduleSlotKey(left)
    const rightSlot = parseScheduleSlotKey(right)

    if (!leftSlot || !rightSlot) {
      return `${left}`.localeCompare(`${right}`)
    }

    if (leftSlot.dayValue !== rightSlot.dayValue) {
      return leftSlot.dayValue - rightSlot.dayValue
    }

    return leftSlot.periodValue - rightSlot.periodValue
  })
}

export const isCanonicalScheduleValue = value => {
  if (!value) {
    return false
  }

  return `${value}`
    .split('|')
    .every(segment => CANONICAL_SEGMENT_PATTERN.test(segment))
}

export const parseScheduleValue = value => {
  if (!value || !isCanonicalScheduleValue(value)) {
    return []
  }

  const slots = []

  for (const segment of `${value}`.split('|')) {
    const [dayRaw, periodsRaw] = segment.split('@')
    const dayValue = Number(dayRaw)

    for (const periodRaw of `${periodsRaw}`.split(',')) {
      const periodValue = Number(periodRaw)
      slots.push(buildScheduleSlotKey(dayValue, periodValue))
    }
  }

  return normalizeSlots(slots)
}

export const serializeScheduleSlots = slots => {
  const normalizedSlots = normalizeSlots(slots)

  if (!normalizedSlots.length) {
    return ''
  }

  const groupedByDay = new Map()

  for (const slot of normalizedSlots) {
    const parsedSlot = parseScheduleSlotKey(slot)

    if (!parsedSlot) {
      continue
    }

    if (!groupedByDay.has(parsedSlot.dayValue)) {
      groupedByDay.set(parsedSlot.dayValue, [])
    }

    groupedByDay.get(parsedSlot.dayValue).push(parsedSlot.periodValue)
  }

  return [...groupedByDay.entries()]
    .sort((left, right) => left[0] - right[0])
    .map(([dayValue, periodValues]) => `${dayValue}@${periodValues.sort((left, right) => left - right).join(',')}`)
    .join('|')
}

export const formatScheduleSlots = (slots, { showTime = true } = {}) => {
  const normalizedSlots = normalizeSlots(slots)

  if (!normalizedSlots.length) {
    return ''
  }

  const groupedByDay = new Map()

  for (const slot of normalizedSlots) {
    const parsedSlot = parseScheduleSlotKey(slot)

    if (!parsedSlot) {
      continue
    }

    if (!groupedByDay.has(parsedSlot.dayValue)) {
      groupedByDay.set(parsedSlot.dayValue, [])
    }

    groupedByDay.get(parsedSlot.dayValue).push(parsedSlot.periodValue)
  }

  return [...groupedByDay.entries()]
    .sort((left, right) => left[0] - right[0])
    .map(([dayValue, periodValues]) => {
      const dayLabel = DAY_MAP[dayValue]?.label || `周${dayValue}`
      const periodLabels = periodValues
        .sort((left, right) => left - right)
        .map(periodValue => {
          const period = PERIOD_MAP[periodValue]

          if (!period) {
            return `第${periodValue}小节`
          }

          return showTime ? `${period.label}(${period.time})` : period.label
        })

      return `${dayLabel} ${periodLabels.join('、')}`
    })
    .join('；')
}

export const formatScheduleValue = (value, options) => {
  const slots = parseScheduleValue(value)

  if (slots.length) {
    return formatScheduleSlots(slots, options)
  }

  return value || ''
}
