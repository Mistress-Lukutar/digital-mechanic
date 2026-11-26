// Thin fetch helpers for the Digital Mechanic API.

import type {
  AuthMeResponse,
  AuthTokenResponse,
  DocumentInfo,
  DocumentPage,
  VehicleDetail,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// ---------------------------------------------------------------------------
// Auth store — read by apiGet / apiSend to attach Bearer token.
// ---------------------------------------------------------------------------

let _token: string | null = null

export function setAuthToken(token: string | null): void {
  _token = token
}

/** Read the current stored token. */
export function getAuthToken(): string | null {
  return _token
}

// ---------------------------------------------------------------------------
// Public helpers
// ---------------------------------------------------------------------------

/** GET with optional Bearer token (attached from internal store). */
async function apiGetInternal<T>(url: string, authHeader: string | null): Promise<T> {
  const headers: Record<string, string> = {}
  if (authHeader) headers['Authorization'] = `Bearer ${authHeader}`
  const response = await fetch(url, { headers })
  if (!response.ok) {
    const detail = await response.text()
    throw new ApiError(response.status, detail || `HTTP ${response.status}`)
  }
  return (await response.json()) as T
}

/** POST/PUT/DELETE with optional Bearer token. */
async function apiSendInternal<T>(
  url: string,
  method: 'POST' | 'PUT' | 'DELETE',
  body: unknown | undefined,
  authHeader: string | null,
): Promise<T> {
  const headers: Record<string, string> = {}
  if (authHeader) headers['Authorization'] = `Bearer ${authHeader}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const response = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) {
    let message = `HTTP ${response.status}`
    try {
      const payload = await response.json()
      if (payload.detail) message = String(payload.detail)
    } catch {
      /* keep default message */
    }
    throw new ApiError(response.status, message)
  }
  return (await response.json()) as T
}

// ---------------------------------------------------------------------------
// Public API — unauthenticated
// ---------------------------------------------------------------------------

/** GET without any auth header. */
export async function apiGetAuthless<T>(url: string): Promise<T> {
  return apiGetInternal<T>(url, null)
}

/** POST without any auth header. */
export async function apiSendAuthless<T>(
  url: string,
  method: 'POST' | 'PUT' | 'DELETE',
  body?: unknown,
): Promise<T> {
  return apiSendInternal<T>(url, method, body, null)
}

// ---------------------------------------------------------------------------
// Public API — authenticated (reads from _token store)
// ---------------------------------------------------------------------------

/** GET with Bearer token from internal store. */
export async function apiGet<T>(url: string): Promise<T> {
  return apiGetInternal<T>(url, _token)
}

/** POST/PUT/DELETE with Bearer token from internal store. */
export async function apiSend<T>(
  url: string,
  method: 'POST' | 'PUT' | 'DELETE',
  body?: unknown,
): Promise<T> {
  return apiSendInternal<T>(url, method, body, _token)
}

// ---------------------------------------------------------------------------
// Auth helpers (for login / me endpoints that toggle token)
// ---------------------------------------------------------------------------

/** Login: send creds unauthenticated, store returned token. */
export async function login(username: string, password: string): Promise<AuthTokenResponse> {
  const result = await apiSendAuthless<AuthTokenResponse>(
    '/api/auth/login',
    'POST',
    { username, password },
  )
  setAuthToken(result.token)
  return result
}

/** GET /api/auth/me with current token; returns profile. */
export async function getMe(): Promise<AuthMeResponse> {
  return apiGet<AuthMeResponse>('/api/auth/me')
}

/** Change password — needs old + new, uses current token. */
export async function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  await apiSend<void>(
    '/api/auth/change_password',
    'POST',
    { old_password: oldPassword, new_password: newPassword },
  )
}

/** Clear stored token (call on logout). */
export function logoutToken(): void {
  setAuthToken(null)
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

export function formatIso(value: string | null | undefined): string {
  if (!value) return '—'
  const iso = value.endsWith('Z') || value.includes('+') ? value : value + 'Z'
  const date = new Date(iso)
  return isNaN(date.getTime()) ? value : date.toLocaleString('ru-RU', { hour12: false })
}

// ---------------------------------------------------------------------------
// Chat / Vehicle detail / Tickets / Documents helpers
// ---------------------------------------------------------------------------

/** GET /api/vehicles/{vehicle_id} — vehicle detail with sessions & tickets. */
export async function getVehicleDetail(vehicleId: string): Promise<VehicleDetail> {
  return apiGet<VehicleDetail>(`/api/vehicles/${encodeURIComponent(vehicleId)}`)
}

/** POST /api/chat/{vehicle_id}/reset */
export async function resetChat(vehicleId: string): Promise<{ status: string }> {
  return apiSend<{ status: string }>(
    `/api/chat/${encodeURIComponent(vehicleId)}/reset`,
    'POST',
  )
}

/** POST /api/tickets — create a ticket. */
export async function createTicket(
  payload: Record<string, unknown>,
): Promise<{ ticket_id: string; status: string; ticket_record: Record<string, unknown> }> {
  return apiSend<{ ticket_id: string; status: string; ticket_record: Record<string, unknown> }>(
    '/api/tickets',
    'POST',
    payload,
  )
}

/** GET /api/documents — list all documents. */
export async function listDocuments(): Promise<DocumentInfo[]> {
  return apiGet<DocumentInfo[]>('/api/documents')
}

/** GET /api/documents/{doc_id}/page/{page_pdf} */
export async function getDocumentPage(
  docId: string,
  pagePdf: number,
): Promise<DocumentPage> {
  return apiGet<DocumentPage>(
    `/api/documents/${encodeURIComponent(docId)}/page/${pagePdf}`,
  )
}
