import type { ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'

interface Props {
  title: string
  count?: number
  children: ReactNode
  defaultOpen?: boolean
}

export default function EvidencePanel({ title, count, children, defaultOpen = false }: Props) {
  return (
    <details className="group rounded-xl border border-slate-200 bg-white" open={defaultOpen || undefined}>
      <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-semibold text-slate-800">
        <span>{title}{count !== undefined ? ` · ${count}` : ''}</span>
        <ChevronDown className="h-4 w-4 text-slate-400 transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t border-slate-100 px-4 py-3">{children}</div>
    </details>
  )
}
