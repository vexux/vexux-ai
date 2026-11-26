import { AlertTriangle, Database, Network, SearchCheck } from 'lucide-react'
import type { InvestigationReport as Report } from '../types'
import EvidencePanel from './EvidencePanel'

interface Props { report: Report }

function value(record: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    if (record[key] !== undefined && record[key] !== null) return String(record[key])
  }
  return '—'
}

const riskStyles = {
  low: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  medium: 'bg-amber-50 text-amber-700 border-amber-200',
  high: 'bg-red-50 text-red-700 border-red-200'
}

export default function InvestigationReport({ report }: Props) {
  const { summary, mysql, neo4j } = report
  const relational = report.sqlite ?? mysql
  return (
    <div className="mt-3 space-y-3">
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400"><SearchCheck className="h-4 w-4" /> Investigation summary</div>
            <h3 className="mt-1 text-lg font-bold text-slate-900">{summary.customer_name || summary.customer_id}</h3>
            <p className="text-sm text-slate-500">Customer {summary.customer_id}</p>
          </div>
          <span className={`rounded-full border px-3 py-1 text-xs font-bold uppercase ${riskStyles[summary.risk_assessment]}`}>{summary.risk_assessment} risk</span>
        </div>
        {summary.findings.length > 0 ? (
          <div className="mt-4 space-y-2">
            {summary.findings.map((finding, index) => (
              <div key={index} className="flex gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />{finding}</div>
            ))}
          </div>
        ) : <p className="mt-4 text-sm text-slate-500">No deterministic findings were returned.</p>}
        {summary.contributing_signals.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {summary.contributing_signals.map((signal) => <span key={signal} className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-600">{signal.replaceAll('_', ' ')}</span>)}
          </div>
        )}
      </section>

      <EvidencePanel title="SQLite evidence" count={relational.transactions.length + relational.fraud_alerts.length + relational.investigation_records.length} defaultOpen>
        <div className="space-y-4">
          {(['transactions', 'fraud_alerts', 'investigation_records'] as const).map((key) => {
            const rows = relational[key]
            const label = key === 'transactions' ? 'Transactions' : key === 'fraud_alerts' ? 'Fraud alerts' : 'Investigations'
            return (
              <div key={key}>
                <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-slate-500"><Database className="h-3.5 w-3.5" />{label} · {rows.length}</div>
                {rows.length === 0 ? <p className="text-sm text-slate-400">No records returned.</p> : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead><tr className="border-b border-slate-100 text-slate-400">{(key === 'transactions' ? ['transaction_id','amount','currency','status','occurred_at'] : key === 'fraud_alerts' ? ['alert_id','alert_type','severity','status','transaction_id'] : ['investigation_id','fraud_case_id','status']).map((column) => <th key={column} className="px-2 py-2 font-semibold">{column.replaceAll('_',' ')}</th>)}</tr></thead>
                      <tbody>{rows.map((row, index) => (
                        <tr key={index} className="border-b border-slate-50 text-slate-700">
                          {(key === 'transactions' ? ['transaction_id','amount','currency','status','occurred_at'] : key === 'fraud_alerts' ? ['alert_id','alert_type','severity','status','transaction_id'] : ['investigation_id','fraud_case_id','status']).map((column) => <td key={column} className="px-2 py-2 whitespace-nowrap">{value(row,[column])}</td>)}
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </EvidencePanel>

      <EvidencePanel title="Neo4j evidence" count={neo4j.relationships.length + neo4j.nodes.length}>
        {neo4j.relationships.length === 0 && neo4j.nodes.length === 0 ? <p className="text-sm text-slate-400">No graph evidence returned.</p> : (
          <div className="space-y-2">
            {neo4j.relationships.map((relationship, index) => (
              <div key={index} className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700"><Network className="h-4 w-4 text-blue-500" /><span className="font-medium">{value(relationship,['source'])}</span><span className="rounded bg-blue-100 px-2 py-0.5 text-xs font-semibold text-blue-700">{value(relationship,['type'])}</span><span className="font-medium">{value(relationship,['target'])}</span></div>
            ))}
            {neo4j.nodes.length > 0 && <p className="pt-2 text-xs text-slate-400">Connected nodes: {neo4j.nodes.map((node) => value(node,['id'])).filter((id) => id !== '—').join(', ')}</p>}
          </div>
        )}
      </EvidencePanel>

      {report.rag_references.length > 0 && (
        <EvidencePanel title="RAG references" count={report.rag_references.length}>
          <div className="space-y-2">{report.rag_references.map((reference, index) => (
            <div key={index} className="rounded-lg border border-slate-100 px-3 py-2 text-sm">
              <div className="font-semibold text-slate-700">{value(reference,['document_name','source'])}</div>
              {value(reference,['section_title']) !== '—' && <div className="text-xs text-slate-500">Section: {value(reference,['section_title'])}</div>}
            </div>
          ))}</div>
        </EvidencePanel>
      )}

      <EvidencePanel title="Execution trace" count={report.request_id ? 1 : 0}>
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div><dt className="text-xs text-slate-400">Request ID</dt><dd className="break-all font-mono text-xs text-slate-700">{report.request_id}</dd></div>
          <div><dt className="text-xs text-slate-400">Assessment</dt><dd className="text-slate-700">Deterministic service result</dd></div>
          <div className="sm:col-span-2"><dt className="text-xs text-slate-400">Resources consulted</dt><dd className="text-slate-700">{summary.resources_consulted.join(', ') || 'None'}</dd></div>
        </dl>
      </EvidencePanel>
    </div>
  )
}
