import { ReactNode } from 'react'

interface ChartCardProps {
  title: string
  children: ReactNode
  className?: string
}

export default function ChartCard({ title, children, className }: ChartCardProps) {
  return (
    <div className={`card ${className || ''}`}>
      <h3 className="text-sm font-medium text-gray-400 mb-4">{title}</h3>
      {children}
    </div>
  )
}
