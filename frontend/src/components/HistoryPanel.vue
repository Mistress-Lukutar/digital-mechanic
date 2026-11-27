<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import type { SessionRecord, TicketRecord } from '../types'
import { getVehicleDetail } from '../api'
import { formatIso } from '../api'
import AnomalyChart from './AnomalyChart.vue'
import { t } from '../i18n'

const props = defineProps<{
  vehicleId: string
  /** Bump to re-read the vehicle history (e.g. after a ticket is filed). */
  refreshKey?: number
}>()

const emit = defineEmits<{
  'select-session': [sessionId: string]
}>()

const sessions = ref<SessionRecord[]>([])
const tickets = ref<TicketRecord[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

async function load(): Promise<void> {
  if (!props.vehicleId) return
  loading.value = true
  try {
    const data = await getVehicleDetail(props.vehicleId)
    sessions.value = data.sessions ?? []
    tickets.value = data.tickets ?? []
  } catch (e: unknown) {
    if (e instanceof Error) {
      error.value = e.message
    } else {
      error.value = 'Ошибка загрузки истории'
    }
  } finally {
    loading.value = false
  }
}

watch(() => props.refreshKey, (key) => {
  if (key) load()
})

onMounted(load)

function sessionBadgeClass(status: SessionRecord['status']): string {
  switch (status) {
    case 'normal': return 'badge-ok'
    case 'anomaly': return 'badge-warning'
    case 'check_failed': return 'badge-danger'
    default: return ''
  }
}

function sessionLabel(status: SessionRecord['status']): string {
  switch (status) {
    case 'normal': return t('status.label.normal')
    case 'anomaly': return t('status.label.anomaly')
    case 'check_failed': return t('status.label.check_failed')
    default: return status || '—'
  }
}

function urgencyChipClass(urgency: string): string {
  switch (urgency) {
    case 'high': return 'badge-danger'
    case 'medium': return 'badge-warning'
    case 'low': return 'badge-ok'
    default: return ''
  }
}

function urgencyLabel(urgency: string): string {
  switch (urgency) {
    case 'high': return t('history.urgency.high')
    case 'medium': return t('history.urgency.medium')
    case 'low': return t('history.urgency.low')
    default: return urgency
  }
}

function getConclusion(payload: Record<string, unknown>): string {
  const c = payload.conclusion
  return typeof c === 'string' ? c : String(c ?? '')
}

function getUrgency(payload: Record<string, unknown>): string {
  const u = payload.urgency
  return typeof u === 'string' ? u : 'medium'
}

interface ScoreTrendWorsening { kind: 'worsening'; n: number }
interface ScoreTrendImproving { kind: 'improving'; n: number }
type ScoreTrend = ScoreTrendWorsening | ScoreTrendImproving | { kind: 'stable' } | null

const scoreTrend = computed<ScoreTrend>(() => {
  const points = sessions.value
    .filter(s => s.anomaly_score != null && s.checked_at != null)
    .sort((a, b) => (a.checked_at ?? '').localeCompare(b.checked_at ?? ''))
    .slice(-5)

  if (points.length < 3) return null

  const scores = points.map(p => p.anomaly_score!)

  // Strict consecutive run terminating at the latest check — the caption
  // promises «{n} подряд», so any counter-direction break ends the run.
  let rises = 0
  for (let i = scores.length - 1; i > 0 && scores[i] > scores[i - 1]; i--) rises++
  let falls = 0
  for (let i = scores.length - 1; i > 0 && scores[i] < scores[i - 1]; i--) falls++

  if (rises >= 2) return { kind: 'worsening', n: rises + 1 }
  if (falls >= 2) return { kind: 'improving', n: falls + 1 }
  return { kind: 'stable' }
})

</script>

<template>
  <div class="history-panel panel">
    <h3>{{ t('history.title') }}</h3>

    <!-- Loading -->
    <div v-if="loading" class="history-loading">
      <span class="spinner" />
      <span class="dim">Загрузка…</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="error-strip">
      {{ error }}
    </div>

    <!-- Sessions section -->
    <template v-else>
      <AnomalyChart :sessions="sessions" />

      <span v-if="scoreTrend && scoreTrend.kind === 'worsening'" class="badge badge-warning trend-caption">
        ▲ {{ t('history.trend_worsening', { n: scoreTrend.n }) }}
      </span>
      <span v-else-if="scoreTrend && scoreTrend.kind === 'improving'" class="badge badge-ok trend-caption">
        ▼ {{ t('history.trend_improving', { n: scoreTrend.n }) }}
      </span>
      <span v-else-if="scoreTrend && scoreTrend.kind === 'stable'" class="chip trend-caption">
        → {{ t('history.trend_stable') }}
      </span>

      <section class="history-section">
        <h4 class="section-title">{{ t('history.checks_section') }}</h4>

        <div v-if="sessions.length === 0" class="empty-hint dim">
          {{ t('history.no_checks') }}
        </div>

        <div v-else class="session-list">
          <div
            v-for="s in sessions" :key="s.session_id"
            class="session-item"
            @click="emit('select-session', s.session_id)"
          >
            <span class="session-date dim mono">{{ formatIso(s.checked_at) }}</span>
            <span :class="['badge', sessionBadgeClass(s.status)]">
              {{ sessionLabel(s.status) }}
            </span>

            <div v-if="s.anomaly_title" class="session-anomaly">
              <span class="anomaly-chip">{{ s.anomaly_type }}</span>
              <span class="dim">{{ s.anomaly_title }}</span>
            </div>

            <div v-if="s.anomaly_score !== null && s.confidence !== null" class="session-scores dim mono">
              балл: {{ s.anomaly_score.toFixed(1) }} &middot; уверенность: {{ (s.confidence * 100).toFixed(0) }}%
            </div>
          </div>
        </div>
      </section>

      <!-- Tickets section -->
      <section class="history-section">
        <h4 class="section-title">{{ t('history.tickets_section') }}</h4>

        <div v-if="tickets.length === 0" class="empty-hint dim">
          {{ t('history.no_tickets') }}
        </div>

        <div v-else class="ticket-list">
          <div v-for="t in tickets" :key="t.ticket_id" class="ticket-item">
            <span class="ticket-id mono">{{ t.ticket_id }}</span>
            <span class="ticket-date dim mono">{{ formatIso(t.created_at) }}</span>

            <div class="ticket-info">
              <span class="dim">{{ getConclusion(t.payload) }}</span>
              <span :class="['badge', urgencyChipClass(getUrgency(t.payload))]">
                {{ urgencyLabel(getUrgency(t.payload)) }}
              </span>
            </div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.history-panel {
  padding: 12px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.history-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 0;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-hint {
  font-size: 13px;
  padding: 8px 0;
}

.session-list,
.ticket-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.session-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s;
}

.session-item:hover {
  background: var(--bg-input);
}

.session-date {
  font-size: 11px;
}

.session-anomaly {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.anomaly-chip {
  background: var(--bg-input);
  border: 1px solid var(--border);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  color: var(--text-dim);
  white-space: nowrap;
}

.session-scores {
  font-size: 11px;
}

.ticket-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  background: var(--bg-input);
}

.ticket-id {
  font-size: 12px;
  color: var(--accent);
}

.ticket-date {
  font-size: 11px;
}

.ticket-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.trend-caption {
  display: inline-block;
  margin: 4px 0 8px;
}
</style>
