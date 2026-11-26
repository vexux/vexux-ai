import { useEffect, useState } from 'react'
import { CheckCircle2, CircleHelp, RefreshCw, TriangleAlert } from 'lucide-react'
import { getSystemStatus } from '../api'
import type { SystemStatus as Status } from '../types'

export default function SystemStatusPage() {
  const [status, setStatus] = useState<Status | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true); setError(null)
    try { setStatus(await getSystemStatus()) } catch (err) { setError(err instanceof Error ? err.message : 'Unable to read system status') } finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [])

  const icon = (state: string) => state === 'available' ? <CheckCircle2 className="h-5 w-5 text-teal-600" /> : state === 'configured' ? <CheckCircle2 className="h-5 w-5 text-blue-600" /> : state === 'unavailable' ? <TriangleAlert className="h-5 w-5 text-amber-600" /> : <CircleHelp className="h-5 w-5 text-slate-400" />

  return (
    <main className="h-full overflow-y-auto bg-slate-50 p-6">
      <div className="mx-auto max-w-4xl">
        <div className="flex items-center justify-between"><div><h1 className="text-xl font-bold text-slate-900">System Status</h1><p className="mt-1 text-sm text-slate-500">Safe availability checks for investigation resources.</p></div><button onClick={load} disabled={loading} className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm disabled:opacity-50"><RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />Refresh</button></div>
        {error && <div className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
        {status && <div className="mt-5 grid gap-3 sm:grid-cols-2">
          {Object.entries(status.components).filter(([name]) => name !== 'mysql' || !status.components.sqlite).map(([name, component]) => (
            <section key={name} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-center justify-between"><div className="flex items-center gap-2">{icon(component.state)}<h2 className="font-semibold capitalize text-slate-800">{name === 'sqlite' ? 'SQLite' : name === 'mysql' ? 'MySQL' : name === 'neo4j' ? 'Neo4j' : name === 'rag' ? 'RAG' : name === 'model' ? 'Model provider' : 'FastAPI'}</h2></div><span className="text-xs font-bold uppercase text-slate-400">{component.state}</span></div>
              <p className="mt-3 text-sm text-slate-500">{component.detail}</p>
            </section>
          ))}
        </div>}
      </div>
    </main>
  )
}
