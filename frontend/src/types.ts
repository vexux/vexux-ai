export type RiskLevel = 'low' | 'medium' | 'high'

export interface InvestigationSummary {
  customer_id: string
  customer_name?: string | null
  risk_assessment: RiskLevel
  findings: string[]
  contributing_signals: string[]
  resources_consulted: string[]
  metadata: Record<string, unknown>
}

export interface InvestigationReport {
  summary: InvestigationSummary
  sqlite?: {
    transactions: Record<string, unknown>[]
    fraud_alerts: Record<string, unknown>[]
    investigation_records: Record<string, unknown>[]
  }
  mysql: {
    transactions: Record<string, unknown>[]
    fraud_alerts: Record<string, unknown>[]
    investigation_records: Record<string, unknown>[]
  }
  neo4j: {
    nodes: Record<string, unknown>[]
    relationships: Record<string, unknown>[]
  }
  rag_references: Record<string, unknown>[]
  evidence: Record<string, unknown>[]
  deterministic_assessment: boolean
  request_id: string
}

export interface FraudResponse {
  request_id: string
  session_id: string
  user_id: string
  success: boolean
  output?: unknown
  investigation?: InvestigationReport
  rag_references: Record<string, unknown>[]
  trace: Record<string, unknown>[]
  error?: string
  metadata: Record<string, unknown>
}

export interface StatusComponent {
  state: 'available' | 'configured' | 'unavailable' | 'unknown'
  detail: string
}

export interface SystemStatus {
  status: string
  components: Record<string, StatusComponent>
}
