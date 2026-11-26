<script setup lang="ts">
import type { DiagnosticResult } from '../types'
import { t } from '../i18n'

defineProps<{
  diag: DiagnosticResult | null
}>()

function statusLabel(status: string): string {
  switch (status) {
    case 'normal': return t('status.label.normal')
    case 'anomaly': return t('status.label.anomaly')
    case 'check_failed': return t('status.label.check_failed')
    default: return status || '—'
  }
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'normal': return 'badge-ok'
    case 'anomaly': return 'badge-warning'
    case 'check_failed': return 'badge-danger'
    default: return ''
  }
}

function signalLabel(q: string): string {
  switch (q) {
    case 'good': return t('status.signal.good')
    case 'warning': return t('status.signal.warning')
    case 'bad': return t('status.signal.bad')
    default: return q || '—'
  }
}

function signalBadgeClass(q: string): string {
  switch (q) {
    case 'good': return 'badge-ok'
    case 'warning': return 'badge-warning'
    case 'bad': return 'badge-danger'
    default: return ''
  }
}

function clamp(v: number | null, min = 0, max = 100): number {
  if (v === null) return min
  return Math.min(max, Math.max(min, v))
}
</script>

<template>
  <div v-if="diag" class="status-card panel">
    <!-- Status badge -->
    <div class="status-header">
      <span :class="['badge', statusBadgeClass(diag.status)]">
        {{ statusLabel(diag.status) }}
      </span>

      <span v-if="diag.anomaly_type" class="chip diag-type-chip">
        {{ diag.anomaly_type }}
      </span>
    </div>

    <!-- Anomaly title -->
    <h3 v-if="diag.anomaly_title" class="status-title">{{ diag.anomaly_title }}</h3>

    <!-- Score bars -->
    <div class="score-bars">
      <div class="score-row">
        <span class="score-label">{{ t('status.score.label') }}</span>
        <div class="progress-track">
          <div
            class="progress-fill"
            :style="{ width: `${clamp(diag.anomaly_score ?? 0)}%` }"
            :class="diag.anomaly_score !== null && diag.anomaly_score > 60 ? 'fill-danger' : 'fill-ok'"
          />
        </div>
        <span class="score-value">{{ diag.anomaly_score !== null ? diag.anomaly_score.toFixed(1) : '—' }}</span>
      </div>

      <div class="score-row">
        <span class="score-label">{{ t('status.confidence.label') }}</span>
        <div class="progress-track">
          <div
            class="progress-fill"
            :style="{ width: `${clamp(diag.confidence ?? 0)}%` }"
            :class="'fill-ok'"
          />
        </div>
        <span class="score-value">{{ diag.confidence !== null ? `${(diag.confidence * 100).toFixed(0)}%` : '—' }}</span>
      </div>
    </div>

    <!-- Signal quality -->
    <div class="signal-row">
      <span class="dim">{{ t('status.signal.label') }}</span>
      <span :class="['badge', signalBadgeClass(diag.signal_quality)]">
        {{ signalLabel(diag.signal_quality) }}
      </span>
    </div>

    <!-- Check failed warning -->
    <div v-if="diag.status === 'check_failed'" class="info-strip check-failed-warn">
      {{ t('status.check_failed_warning') }}
    </div>

    <!-- Description -->
    <p v-if="diag.description" class="status-desc">{{ diag.description }}</p>

    <!-- Session info -->
    <div class="session-meta dim mono">
      {{ diag.session_id }} &middot; {{ diag.model_version || '—' }}
    </div>
  </div>
</template>

<style scoped>
.status-card {
  margin-bottom: 12px;
}

.status-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.diag-type-chip {
  background: var(--bg-input);
  border: 1px solid var(--border);
  color: var(--text-dim);
}

.status-title {
  font-size: 14px;
  font-weight: 600;
  margin: 4px 0 8px;
  color: var(--text);
}

.score-bars {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 8px;
}

.score-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.score-label {
  color: var(--text-dim);
  width: 70px;
  flex-shrink: 0;
}

.progress-track {
  flex: 1;
  height: 8px;
  background: var(--bg-input);
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.fill-ok {
  background: var(--accent);
}

.fill-danger {
  background: var(--warning);
}

.score-value {
  width: 50px;
  text-align: right;
  color: var(--text-dim);
  font-size: 12px;
  flex-shrink: 0;
}

.signal-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  margin-bottom: 8px;
}

.check-failed-warn {
  margin-bottom: 8px;
}

.status-desc {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text);
  margin: 0 0 6px;
}

.session-meta {
  font-size: 11px;
  color: var(--text-dim);
}
</style>
