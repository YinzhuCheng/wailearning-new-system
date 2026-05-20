export function normalizeBrandingText(value) {
  return value
}

export function normalizeSystemSettings(settings) {
  if (!settings || typeof settings !== 'object') {
    return settings
  }

  return {
    ...settings,
    system_name: normalizeBrandingText(settings.system_name),
    copyright: normalizeBrandingText(settings.copyright)
  }
}
