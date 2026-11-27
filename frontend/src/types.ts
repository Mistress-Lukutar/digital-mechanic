// API types for the Digital Mechanic backend.

export type UserRole = 'user' | 'admin'
export type VehicleStatus = 'normal' | 'anomaly' | 'check_failed' | null
export type VehicleGroup = 'normal' | 'attention' | 'quarantine'

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface AuthLoginPayload {
  username: string
  password: string
}

export interface AuthTokenResponse {
  token: string
  username: string
  role: UserRole
  must_change_password: boolean
}

export interface AuthMeResponse {
  username: string
  role: UserRole
  must_change_password: boolean
}

export interface ChangePasswordPayload {
  old_password: string
  new_password: string
}

// ---------------------------------------------------------------------------
// Vehicle (listing item — GET /api/vehicles)
// ---------------------------------------------------------------------------

export interface VehicleItem {
  vehicle_id: string
  garage_no: string
  make: string
  model: string | null
  vehicle_type: string
  engine_model: string
  fuel: string
  latest_status: VehicleStatus
  latest_checked_at: string | null
  latest_anomaly_type: string | null
  latest_anomaly_title: string | null
  latest_anomaly_score: number | null
  anomaly_count: number
  check_count: number
  group: VehicleGroup
}

// ---------------------------------------------------------------------------
// Vehicle detail (GET /api/vehicles/{id})
// ---------------------------------------------------------------------------

export interface SessionRecord {
  session_id: string
  checked_at: string | null
  status: 'normal' | 'anomaly' | 'check_failed'
  anomaly_type: string | null
  anomaly_title: string | null
  anomaly_score: number | null
  confidence: number | null
  signal_quality: 'good' | 'warning' | 'bad'
  description: string
}

export interface TicketRecord {
  ticket_id: string
  created_at: string
  payload: Record<string, unknown>
}

export interface VehicleDetail {
  vehicle_id: string
  garage_no: string
  make: string
  model: string
  vehicle_type: string
  engine_model: string
  fuel: string
  sessions: SessionRecord[]
  tickets: TicketRecord[]
}

// ---------------------------------------------------------------------------
// Fleet stats (GET /api/fleet/stats)
// ---------------------------------------------------------------------------

export interface FleetStats {
  total: number
  normal: number
  attention: number
  quarantine: number
}

// ---------------------------------------------------------------------------
// Chat / SSE
// ---------------------------------------------------------------------------

/** One chat conversation in the per-vehicle history list. */
export interface ChatConversationItem {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

/** One persisted message inside a conversation. */
export interface ChatHistoryMessage {
  id: number
  parent_id: number | null
  sibling_index: number
  sibling_count: number
  prev_sibling_id: number | null
  next_sibling_id: number | null
  role: 'user' | 'assistant'
  text: string
  image: string | null
  ts: string
}

/** Response of GET /api/chats/{id}. */
export interface ChatConversationDetail {
  conversation: ChatConversationItem & { username: string; vehicle_id: string }
  messages: ChatHistoryMessage[]
}

export interface AgentStepT {
  call_id: string
  name: string
  summary: string | null
  content: string | null
  is_error: boolean
  done: boolean
}

export interface ChatMessage {
  id?: number
  siblingIndex?: number
  siblingCount?: number
  prevSiblingId?: number | null
  nextSiblingId?: number | null
  role: 'user' | 'assistant'
  text: string
  steps: AgentStepT[]
  reasoning?: string
  image?: string
}

// ---------------------------------------------------------------------------
// Ticket / TicketPayload
// ---------------------------------------------------------------------------

export interface ReferenceEntry {
  manual: string
  pdf_page: number
}

export interface TicketPayload {
  vehicle_id: string
  session_id: string
  anomaly_type: string
  conclusion: string
  urgency: 'low' | 'medium' | 'high'
  operations: string[]
  spare_parts: string[]
  references: ReferenceEntry[]
}

export interface TicketDraftEvent {
  payload: TicketPayload
  priority_rationale: string
  urgency_source: 'agent' | 'rules'
  session_id: string
}

// ---------------------------------------------------------------------------
// Diagnostic result (parsed from get_diagnostic_result tool_result content)
// ---------------------------------------------------------------------------

export interface DiagnosticResult {
  status: 'normal' | 'anomaly' | 'check_failed' | string
  anomaly_type: string | null
  anomaly_title: string | null
  anomaly_score: number | null
  confidence: number | null
  signal_quality: 'good' | 'warning' | 'bad' | string
  description: string
  session_id: string
  model_version: string
}

// ---------------------------------------------------------------------------
// Document types
// ---------------------------------------------------------------------------

export interface DocumentInfo {
  doc_id: string
  doc_title: string
  pages: number[]
  engines: string[]
  file: string
}

// ---------------------------------------------------------------------------
// SSE event shapes
// ---------------------------------------------------------------------------

export interface SseTokenEvent {
  text: string
}

export interface SseReasoningEvent {
  text: string
}

export interface SseToolStartEvent {
  call_id: string
  name: string
  arguments: string
}

export interface SseToolResultEvent {
  call_id: string
  name: string
  summary: string
  content: string
  is_error: boolean
}

export interface SseDocumentEvent {
  doc_id: string
  doc_title: string
  page_pdf: number
  pdf_path: string
  has_text: boolean
}

export interface SseTurnDoneEvent {
  stop_reason: string | null
  usage: { input_tokens: number; output_tokens: number } | null
}

export interface SseErrorEvent {
  message: string
}

// ---------------------------------------------------------------------------
// Admin — usage & users
// ---------------------------------------------------------------------------

export interface UsageTotals {
  requests_total: number
  requests_error: number
  input_tokens: number
  output_tokens: number
}

export interface UsageRowItem {
  id: number
  ts: string
  username: string | null
  vehicle_id: string | null
  kind: string
  model: string | null
  input_tokens: number
  output_tokens: number
  duration_ms: number
  status: string
  error: string | null
}

export interface ChatTurnDetail {
  question: string
  answer: string
  tools: string[]
  citations: { doc: string; page: number }[]
  ticket_draft: { anomaly_type: string | null; urgency: string | null } | null
  has_image: boolean
  language: string | null
}

export interface AdminUserItem {
  username: string
  role: string
  must_change_password: boolean
  created_at: string
}

// ---------------------------------------------------------------------------
// Admin — LLM settings
// ---------------------------------------------------------------------------

export interface LlmSettingsView {
  protocol: string
  base_url: string
  api_key: string
  model: string
  temperature: number | null
  max_output_tokens: number | null
}
