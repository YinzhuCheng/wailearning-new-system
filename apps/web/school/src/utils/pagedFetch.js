export const loadAllPages = async (loader, { pageSize = 100, maxPages = 50 } = {}) => {
  const items = []
  let page = 1
  let total = 0

  while (page <= maxPages) {
    const result = await loader({ page, page_size: pageSize })
    const pageItems = Array.isArray(result?.data) ? result.data : []
    total = Number(result?.total || pageItems.length)
    items.push(...pageItems)

    if (!result?.total || items.length >= total || pageItems.length < pageSize) {
      break
    }

    page += 1
  }

  return items
}
