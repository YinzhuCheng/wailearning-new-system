/**
 * In-app notification refresh: polling + BroadcastChannel so open tabs stay in sync
 * without manual reload after new notices are published or created server-side.
 */

const BROADCAST_CHANNEL = 'courseeval-notification-sync'
/** Header and list refresh interval; keep low enough for timely toasts without hammering `/api/notifications/sync-status`. */
export const DEFAULT_NOTIFICATION_POLL_INTERVAL_MS = 12_000
const DEFAULT_POLL_INTERVAL_MS = DEFAULT_NOTIFICATION_POLL_INTERVAL_MS

const listeners = new Set()

export function onNotificationRefresh(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export function emitNotificationRefresh() {
  listeners.forEach(fn => {
    try {
      fn()
    } catch (error) {
      console.error('notification refresh listener failed', error)
    }
  })
}

export function broadcastNotificationChange() {
  try {
    const channel = new BroadcastChannel(BROADCAST_CHANNEL)
    channel.postMessage({ type: 'notifications_changed', ts: Date.now() })
    channel.close()
  } catch {
    /* BroadcastChannel unsupported */
  }
}

export function subscribeNotificationBroadcast(handler) {
  if (typeof BroadcastChannel === 'undefined') {
    return () => {}
  }
  const channel = new BroadcastChannel(BROADCAST_CHANNEL)
  channel.onmessage = event => {
    if (event?.data?.type === 'notifications_changed') {
      handler()
    }
  }
  return () => channel.close()
}

export function startNotificationPolling(handler, intervalMs = DEFAULT_POLL_INTERVAL_MS) {
  const id = window.setInterval(() => {
    if (document.visibilityState === 'visible') {
      handler()
    }
  }, intervalMs)
  return () => window.clearInterval(id)
}
