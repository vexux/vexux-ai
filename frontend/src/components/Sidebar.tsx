import { Activity, Bot, Plus } from 'lucide-react'
import { NavLink } from 'react-router-dom'

interface Props { onNewConversation: () => void }

export default function Sidebar({ onNewConversation }: Props) {
  return (
    <aside className="flex h-full w-[224px] shrink-0 flex-col bg-slate-950 px-3 py-4 text-slate-200">
      <div className="flex items-center gap-2 px-2 pb-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold text-white">V</div>
        <div><div className="text-sm font-bold text-white">Vexux AI</div><div className="text-[11px] text-slate-400">Fraud Intelligence</div></div>
      </div>
      <nav className="space-y-1">
        <NavLink to="/" className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm ${isActive ? 'bg-slate-800 text-white' : 'text-slate-300 hover:bg-slate-900'}`}><Bot className="h-4 w-4" />AI Investigator</NavLink>
        <NavLink to="/status" className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm ${isActive ? 'bg-slate-800 text-white' : 'text-slate-300 hover:bg-slate-900'}`}><Activity className="h-4 w-4" />System Status</NavLink>
      </nav>
      <button onClick={onNewConversation} className="mt-5 flex items-center justify-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-900"><Plus className="h-4 w-4" />New conversation</button>
      <div className="mt-auto px-2 text-[11px] text-slate-500">Investigator workspace</div>
    </aside>
  )
}
