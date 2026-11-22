import { useEffect, useRef, useState } from 'react'
import { LoaderCircle, Send, Wifi, WifiOff } from 'lucide-react'
import { checkHealth, investigate } from '../api'
import type { FraudResponse } from '../types'
import InvestigationReport from './InvestigationReport'

interface Message { id: string; role: 'user' | 'assistant'; text?: string; response?: FraudResponse }

const starters = [
  'Investigate a customer',
  'Find suspicious transaction patterns',
  'Examine shared-device relationships',
  'Explain a customer risk assessment'
]

export default function ChatWorkspace() {
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID())
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [executing, setExecuting] = useState(false)
  const [connected, setConnected] = useState<boolean | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => { void checkHealth().then(setConnected); const timer = window.setInterval(() => void checkHealth().then(setConnected), 15000); return () => window.clearInterval(timer) }, [])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, executing])

  const submit = async (text?: string) => {
    const query = (text ?? input).trim()
    if (!query || executing) return
    setInput('')
    setExecuting(true)
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'user', text: query }])
    try {
      const response = await investigate(query, sessionId)
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', text: response.success ? undefined : response.error || 'The investigation could not be completed.', response }])
    } catch (error) {
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', text: error instanceof Error ? error.message : 'Backend connection failed.' }])
    } finally { setExecuting(false) }
  }

  const newConversation = () => { setSessionId(crypto.randomUUID()); setMessages([]); setInput('') }

  return (
    <main className="flex h-full min-h-0 flex-col bg-slate-50">
      <header className="flex h-[72px] shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
        <div><h1 className="text-lg font-bold text-slate-900">AI Investigator</h1><p className="mt-0.5 text-xs text-slate-500">Evidence-led fraud investigation workspace</p></div>
        <div className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold ${connected ? 'border-teal-200 bg-teal-50 text-teal-700' : connected === false ? 'border-red-200 bg-red-50 text-red-700' : 'border-slate-200 bg-slate-50 text-slate-500'}`}>{connected ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}{connected ? 'Backend connected' : connected === false ? 'Backend offline' : 'Checking'}</div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-6 py-6">
          {messages.length === 0 && (
            <div className="mx-auto mt-12 max-w-2xl text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-blue-600 text-xl font-bold text-white">V</div>
              <h2 className="mt-4 text-xl font-bold text-slate-900">Start a fraud investigation</h2>
              <p className="mt-2 text-sm text-slate-500">Use a customer ID to retrieve authoritative customer, transaction, alert, graph, and reference evidence.</p>
              <div className="mt-6 grid gap-2 sm:grid-cols-2">{starters.map((prompt) => <button key={prompt} onClick={() => setInput(prompt === 'Investigate a customer' ? 'Investigate customer ' : prompt)} className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-700 shadow-sm hover:border-blue-300 hover:bg-blue-50">{prompt}</button>)}</div>
            </div>
          )}
          <div className="space-y-5">
            {messages.map((message) => (
              <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                {message.role === 'user' ? (
                  <div className="max-w-[80%] rounded-2xl rounded-br-md bg-blue-600 px-4 py-3 text-sm text-white shadow-sm">{message.text}</div>
                ) : (
                  <div className="w-full max-w-[920px]">
                    <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-500"><span className="flex h-6 w-6 items-center justify-center rounded-md bg-slate-900 text-[10px] text-white">V</span>Vexux Investigator</div>
                    {message.text && <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 shadow-sm">{message.text}</div>}
                    {message.response?.investigation && <InvestigationReport report={message.response.investigation} />}
                    {message.response?.success && typeof message.response.output === 'string' && <div className="mt-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 shadow-sm">{message.response.output}</div>}
                    {message.response?.rag_references && message.response.rag_references.length > 0 && <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3"><div className="text-xs font-bold uppercase text-slate-400">RAG references</div>{message.response.rag_references.map((reference, index) => <div key={index} className="mt-2 text-sm text-slate-700">{String(reference.document_name || reference.source || 'Reference')}{reference.section_title ? ` — ${String(reference.section_title)}` : ''}</div>)}</div>}
                  </div>
                )}
              </div>
            ))}
            {executing && <div className="flex items-center gap-2 text-sm text-slate-500"><LoaderCircle className="h-4 w-4 animate-spin" />Running investigation workflow...</div>}
            <div ref={endRef} />
          </div>
        </div>
      </div>

      <div className="shrink-0 border-t border-slate-200 bg-white px-6 py-4">
        <div className="mx-auto max-w-4xl">
          <div className="flex items-end gap-2 rounded-xl border border-slate-300 bg-white p-2 shadow-sm focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100">
            <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submit() } }} rows={2} placeholder="Ask to investigate a customer or follow up..." className="max-h-32 min-h-[44px] flex-1 resize-none border-0 px-2 py-2 text-sm outline-none" />
            <button onClick={() => void submit()} disabled={!input.trim() || executing} className="mb-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"><Send className="h-4 w-4" /></button>
          </div>
          <div className="mt-2 text-[11px] text-slate-400">Enter to send · Shift+Enter for a new line · Session memory is in-process only</div>
        </div>
      </div>
    </main>
  )
}
