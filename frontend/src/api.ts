// Thin fetch helpers for the Digital Mechanic API.

import type {
  AdminUserItem,
  AuthMeResponse,
  AuthTokenResponse,
  ChatTurnDetail,
  DocumentInfo,
  DocumentPage,
  FleetStats,
  LlmSettingsView,
  UsageRowItem,
  UsageTotals as UsageTotalsType,
  VehicleDetail,
  VehicleItem,
} from './types'

// Base path of the app: '/' under the dev server, './' in the built bundle.
// All request URLs go through apiUrl() so a subpath reverse proxy works.
export const API_BASE: string = import.meta.env.BASE_URL

/** Build an app-relative request URL from an absolute-app path like '/api/x'. */
export function apiUrl(path: string): string {
  return `${API_BASE}${path.replace(/^\/+/, '')}`
}

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

/** Format a FastAPI ``detail`` (plain string or 422 validation list) for display. */
export function formatApiDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const entry = item as { msg?: unknown }
        return typeof entry?.msg === 'string' ? entry.msg : JSON.stringify(item)
      })
      .join('; ')
  }
  if (detail !== undefined && detail !== null) return JSON.stringify(detail)
  return ''
}

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
    // FastAPI errors are JSON {detail: ...} — format like apiSendInternal;
    // fall back to raw text for non-JSON bodies (e.g. proxy errors).
    let message = await response.text()
    try {
      const payload = JSON.parse(message)
      if (payload?.detail) message = formatApiDetail(payload.detail)
    } catch {
      /* keep raw text */
    }
    throw new ApiError(response.status, message || `HTTP ${response.status}`)
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
      if (payload.detail) message = formatApiDetail(payload.detail)
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
    apiUrl('/api/auth/login'),
    'POST',
    { username, password },
  )
  setAuthToken(result.token)
  return result
}

/** GET /api/auth/me with current token; returns profile. */
export async function getMe(): Promise<AuthMeResponse> {
  return apiGet<AuthMeResponse>(apiUrl('/api/auth/me'))
}

/** Change password — needs old + new, uses current token. */
export async function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  await apiSend<void>(
    apiUrl('/api/auth/change_password'),
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
  return apiGet<VehicleDetail>(apiUrl(`/api/vehicles/${encodeURIComponent(vehicleId)}`))
}

/** POST /api/chat/{vehicle_id}/reset */
export async function resetChat(vehicleId: string): Promise<{ status: string }> {
  return apiSend<{ status: string }>(
    apiUrl(`/api/chat/${encodeURIComponent(vehicleId)}/reset`),
    'POST',
  )
}

/** POST /api/tickets — create a ticket. */
export async function createTicket(
  payload: Record<string, unknown>,
): Promise<{ ticket_id: string; status: string; ticket_record: Record<string, unknown> }> {
  return apiSend<{ ticket_id: string; status: string; ticket_record: Record<string, unknown> }>(
    apiUrl('/api/tickets'),
    'POST',
    payload,
  )
}

/** GET /api/documents — list all documents. */
export async function listDocuments(): Promise<DocumentInfo[]> {
  return apiGet<DocumentInfo[]>(apiUrl('/api/documents'))
}

/** GET /api/documents/{doc_id}/page/{page_pdf} */
export async function getDocumentPage(
  docId: string,
  pagePdf: number,
): Promise<DocumentPage> {
  docId = docId.replace(/[«»]/g, '').trim()
  return apiGet<DocumentPage>(
    apiUrl(`/api/documents/${encodeURIComponent(docId)}/page/${pagePdf}`),
  )
}

// ---------------------------------------------------------------------------
// Fleet stats / priority (read by all users)
// ---------------------------------------------------------------------------

/** GET /api/fleet/stats */
export async function getFleetStats(): Promise<FleetStats> {
  return apiGet<FleetStats>(apiUrl('/api/fleet/stats'))
}

/** GET /api/fleet/priority — quarantine vehicles sorted by anomaly_score desc */
export async function getFleetPriority(): Promise<VehicleItem[]> {
  return apiGet<VehicleItem[]>(apiUrl('/api/fleet/priority'))
}

// ---------------------------------------------------------------------------
// Admin — usage
// ---------------------------------------------------------------------------

/** GET /api/admin/usage/totals */
export async function getAdminUsageTotals(): Promise<UsageTotalsType> {
  return apiGet<UsageTotalsType>(apiUrl('/api/admin/usage/totals'))
}

/** GET /api/admin/usage/recent?limit=N */
export async function getAdminUsageRecent(limit: number = 50): Promise<UsageRowItem[]> {
  const limit_ = String(Math.min(200, Math.max(1, limit)))
  return apiGet<UsageRowItem[]>(`${apiUrl('/api/admin/usage/recent')}?limit=${limit_}`)
}

/** GET /api/admin/usage/{id}/detail */
export async function getAdminUsageDetail(id: number): Promise<ChatTurnDetail> {
  return apiGet<ChatTurnDetail>(apiUrl(`/api/admin/usage/${id}/detail`))
}

// ---------------------------------------------------------------------------
// Admin — users CRUD
// ---------------------------------------------------------------------------

/** GET /api/admin/users */
export async function getAdminUsers(): Promise<AdminUserItem[]> {
  return apiGet<AdminUserItem[]>(apiUrl('/api/admin/users'))
}

/** POST /api/admin/users */
export async function createAdminUser(
  username: string,
  password: string,
  role: string,
): Promise<{ status: string }> {
  return apiSend<{ status: string }>(
    apiUrl('/api/admin/users'),
    'POST',
    { username, password, role },
  )
}

/** DELETE /api/admin/users/{username} */
export async function deleteAdminUser(username: string): Promise<{ status: string }> {
  return apiSend<{ status: string }>(
    apiUrl(`/api/admin/users/${encodeURIComponent(username)}`),
    'DELETE',
  )
}

/** POST /api/admin/users/{username}/password */
export async function resetAdminPassword(
  username: string,
  newPassword: string,
): Promise<{ status: string }> {
  return apiSend<{ status: string }>(
    apiUrl(`/api/admin/users/${encodeURIComponent(username)}/password`),
    'POST',
    { new_password: newPassword },
  )
}

// ---------------------------------------------------------------------------
// Admin — LLM settings
// ---------------------------------------------------------------------------

/** GET /api/admin/settings/llm */
export async function getLlmSettings(): Promise<LlmSettingsView> {
  return apiGet<LlmSettingsView>(apiUrl('/api/admin/settings/llm'))
}

/** PUT /api/admin/settings/llm */
export async function updateLlmSettings(params: {
  protocol?: string
  base_url?: string
  api_key?: string
  model?: string
  temperature?: number | null
  max_output_tokens?: number | null
}): Promise<LlmSettingsView> {
  return apiSend<LlmSettingsView>(
    apiUrl('/api/admin/settings/llm'),
    'PUT',
    params,
  )
}
