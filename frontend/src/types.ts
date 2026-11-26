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
