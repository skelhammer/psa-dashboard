import clsx from 'clsx'
import { getTicketSla } from '../utils/formatting'

interface SlaCountdownProps {
  ticket: {
    first_response_due?: string | null
    first_response_violated?: boolean | null
    resolution_due?: string | null
    resolution_violated?: boolean | null
  }
}

export default function SlaCountdown({ ticket }: SlaCountdownProps) {
  const sla = getTicketSla(ticket)
  return (
    <span className={clsx(sla.colorClass, sla.isPulsing && 'sla-violated-pulse')}>
      {sla.text}
    </span>
  )
}
