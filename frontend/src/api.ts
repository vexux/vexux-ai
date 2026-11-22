import type { FraudResponse, SystemStatus } from './types'

const baseUrl = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') || 'http://127.0.0.1:8000'

export async function investigate(query: string, sessionId: string, userId = 'investigator') {
  const response = await fetch(`${baseUrl}/api/v1/fraud/investigate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, session_id: sessionId, user_id: userId })
  })
  if (!response.ok) {
    throw new Error(`Backend request failed (${response.status})`)
  }
  return response.json() as Promise<FraudResponse>
}

export async function getSystemStatus(): Promise<SystemStatus> {
  const response = await fetch(`${baseUrl}/api/v1/status`)
  if (!response.ok) {
    throw new Error(`Status request failed (${response.status})`)
  }
  return response.json()
}

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${baseUrl}/health`)
    return response.ok
  } catch {
    return false
  }
}
