export function formatDuration(totalSeconds?: number | null): string {
  if (!totalSeconds || totalSeconds < 1) {
    return '0m'
  }

  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  if (hours > 0) {
    return `${hours}h ${minutes}m`
  }

  if (minutes > 0) {
    return `${minutes}m`
  }

  return `${seconds}s`
}

export function formatRelativeTime(value?: string): string {
  if (!value) {
    return 'Pending'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'Pending'
  }

  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date)
}

export function humanizeStatus(status?: string | null): string {
  if (!status) {
    return 'Running'
  }

  return status.replace(/_/g, ' ')
}

export function toSentenceCase(input: string): string {
  return input
    .split(' ')
    .filter(Boolean)
    .map((part, index) =>
      index === 0
        ? part.charAt(0).toUpperCase() + part.slice(1).toLowerCase()
        : part.toLowerCase(),
    )
    .join(' ')
}
