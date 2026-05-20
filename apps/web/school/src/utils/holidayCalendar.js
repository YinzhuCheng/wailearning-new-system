const HOLIDAY_PERIODS_BY_YEAR = {
  2025: [
    { name: '元旦', start: '2025-01-01', end: '2025-01-01' },
    { name: '春节', start: '2025-01-28', end: '2025-02-04' },
    { name: '清明节', start: '2025-04-04', end: '2025-04-06' },
    { name: '劳动节', start: '2025-05-01', end: '2025-05-05' },
    { name: '端午节', start: '2025-05-31', end: '2025-06-02' },
    { name: '国庆节/中秋节', start: '2025-10-01', end: '2025-10-08' }
  ],
  2026: [
    { name: '元旦', start: '2026-01-01', end: '2026-01-03' },
    { name: '春节', start: '2026-02-15', end: '2026-02-23' },
    { name: '清明节', start: '2026-04-04', end: '2026-04-06' },
    { name: '劳动节', start: '2026-05-01', end: '2026-05-05' },
    { name: '端午节', start: '2026-06-19', end: '2026-06-21' },
    { name: '中秋节', start: '2026-09-25', end: '2026-09-27' },
    { name: '国庆节', start: '2026-10-01', end: '2026-10-07' }
  ]
}

const ONE_DAY_MS = 24 * 60 * 60 * 1000

const toDateKey = date => {
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

const normalizeDateInput = value => {
  if (!value) {
    return null
  }

  if (value instanceof Date) {
    return new Date(value.getFullYear(), value.getMonth(), value.getDate())
  }

  const rawValue = `${value}`.trim()
  const matchedDate = rawValue.match(/^(\d{4})-(\d{2})-(\d{2})/)

  if (matchedDate) {
    return new Date(Number(matchedDate[1]), Number(matchedDate[2]) - 1, Number(matchedDate[3]))
  }

  const parsedDate = new Date(rawValue)
  if (Number.isNaN(parsedDate.getTime())) {
    return null
  }

  return new Date(parsedDate.getFullYear(), parsedDate.getMonth(), parsedDate.getDate())
}

const collectYearsBetween = (startDate, endDate) => {
  const years = []

  for (let year = startDate.getFullYear(); year <= endDate.getFullYear(); year += 1) {
    years.push(year)
  }

  return years
}

export const buildHolidayMap = (startValue, endValue) => {
  const startDate = normalizeDateInput(startValue)
  const endDate = normalizeDateInput(endValue)

  if (!startDate || !endDate || endDate < startDate) {
    return {}
  }

  const holidayMap = {}

  for (const year of collectYearsBetween(startDate, endDate)) {
    for (const holiday of HOLIDAY_PERIODS_BY_YEAR[year] || []) {
      let currentDate = normalizeDateInput(holiday.start)
      const holidayEnd = normalizeDateInput(holiday.end)

      if (!currentDate || !holidayEnd) {
        continue
      }

      while (currentDate <= holidayEnd) {
        if (currentDate >= startDate && currentDate <= endDate) {
          holidayMap[toDateKey(currentDate)] = {
            name: holiday.name,
            color: '#ef4444'
          }
        }

        currentDate = new Date(currentDate.getTime() + ONE_DAY_MS)
      }
    }
  }

  return holidayMap
}

export const hasHolidayDataForYear = year => Boolean(HOLIDAY_PERIODS_BY_YEAR[year])
