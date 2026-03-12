/**
 * Format minutes into human-readable duration: "2h 15m", "3d 4h", "45m"
 */
export function formatDuration(minutes: number): string {
  if (minutes < 0) return '0m'
  if (minutes < 60) return `${Math.round(minutes)}m`

  const hours = Math.floor(minutes / 60)
  const mins = Math.round(minutes % 60)

  if (hours < 24) {
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`
  }

  const days = Math.floor(hours / 24)
  const remainingHours = hours % 24
  return remainingHours > 0 ? `${days}d ${remainingHours}h` : `${days}d`
}

/**
 * Format minutes into worklog display: "1.5h", "0.25h"
 */
export function formatWorklogHours(minutes: number): string {
  return `${(minutes / 60).toFixed(1)}h`
}

/**
 * Compute age from a datetime string to now, return human-readable string.
 */
export function formatAge(isoString: string): string {
  const created = new Date(isoString)
  const now = new Date()
  const diffMs = now.getTime() - created.getTime()
  const diffMinutes = diffMs / 60000
  return formatDuration(diffMinutes)
}

/**
 * SLA countdown: returns { text, color, isPulsing }
 */
export function slaCountdown(
  dueIso: string | null | undefined,
  violated: boolean | null | undefined
): { text: string; colorClass: string; isPulsing: boolean } {
  if (violated) {
    if (dueIso) {
      const due = new Date(dueIso)
      const now = new Date()
      const overMs = now.getTime() - due.getTime()
      const overMin = overMs / 60000
      return {
        text: `VIOLATED ${formatDuration(overMin)} ago`,
        colorClass: 'text-red-500 font-bold',
        isPulsing: true,
      }
    }
    return { text: 'VIOLATED', colorClass: 'text-red-500 font-bold', isPulsing: true }
  }

  if (!dueIso) {
    return { text: 'No SLA', colorClass: 'text-gray-500', isPulsing: false }
  }

  const due = new Date(dueIso)
  const now = new Date()
  const remainingMs = due.getTime() - now.getTime()
  const remainingMin = remainingMs / 60000

  if (remainingMin <= 0) {
    return {
      text: `VIOLATED ${formatDuration(Math.abs(remainingMin))} ago`,
      colorClass: 'text-red-500 font-bold',
      isPulsing: true,
    }
  }
  if (remainingMin <= 30) {
    return {
      text: `${formatDuration(remainingMin)} left`,
      colorClass: 'text-red-400 font-semibold',
      isPulsing: false,
    }
  }
  if (remainingMin <= 120) {
    return {
      text: `${formatDuration(remainingMin)} left`,
      colorClass: 'text-yellow-400',
      isPulsing: false,
    }
  }
  return {
    text: `${formatDuration(remainingMin)} left`,
    colorClass: 'text-green-400',
    isPulsing: false,
  }
}

/**
 * Get the most urgent SLA info from a ticket's first response and resolution SLAs.
 */
export function getTicketSla(ticket: {
  first_response_due?: string | null
  first_response_time?: string | null
  first_response_violated?: boolean | null
  resolution_due?: string | null
  resolution_violated?: boolean | null
}): { text: string; colorClass: string; isPulsing: boolean } {
  // Check violated first
  if (ticket.first_response_violated) {
    return slaCountdown(ticket.first_response_due, true)
  }
  if (ticket.resolution_violated) {
    return slaCountdown(ticket.resolution_due, true)
  }

  // Skip first response due if already responded
  const frApplies = ticket.first_response_due && !ticket.first_response_time
  const frDue = frApplies ? new Date(ticket.first_response_due!).getTime() : Infinity
  const resDue = ticket.resolution_due ? new Date(ticket.resolution_due).getTime() : Infinity

  if (frDue === Infinity && resDue === Infinity) {
    return { text: 'No SLA', colorClass: 'text-gray-500', isPulsing: false }
  }

  if (frDue <= resDue) {
    return slaCountdown(ticket.first_response_due, false)
  }
  return slaCountdown(ticket.resolution_due, false)
}

/**
 * Get zero-target card color based on count.
 */
export function zeroTargetColor(count: number): string {
  if (count === 0) return 'border-green-500/50 bg-green-500/5'
  if (count <= 2) return 'border-yellow-500/50 bg-yellow-500/5'
  return 'border-red-500/50 bg-red-500/5'
}

export function zeroTargetTextColor(count: number): string {
  if (count === 0) return 'text-green-400'
  if (count <= 2) return 'text-yellow-400'
  return 'text-red-400'
}
