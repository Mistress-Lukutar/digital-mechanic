<script setup lang="ts">
import type { SessionRecord } from '../types'
import { t } from '../i18n'

// B2 display-only chart: anomaly_score over the last checks (no prediction).
const props = defineProps<{
  sessions: SessionRecord[]
}>()

const W = 320
const H = 150
const PADDING_TOP = 18
const PADDING_BOTTOM = 34
const PADDING_LEFT = 36
const PADDING_RIGHT = 10
const INNER_H = H - PADDING_TOP - PADDING_BOTTOM
const INNER_W = W - PADDING_LEFT - PADDING_RIGHT

// Up to 5 latest sessions with a defined score, oldest → newest left→right.
const points: SessionRecord[] = props.sessions
  .filter((s) => s.anomaly_score !== null)
  .slice(0, 5)
  .slice()
  .reverse()

function xPos(i: number): number {
  if (points.length === 1) return PADDING_LEFT + INNER_W / 2
  return PADDING_LEFT + INNER_W * (i / (points.length - 1))
}

function yPos(score: number): number {
  // score 1 → top, score 0 → bottom.
  return PADDING_TOP + INNER_H * (1 - score)
}

function statusColor(status: string): string {
  switch (status) {
    case 'normal': return 'var(--accent)'
    case 'anomaly': return 'var(--danger)'
    case 'check_failed': return 'var(--warning)'
    default: return '#888'
  }
}

function xLabel(s: SessionRecord): string {
  return s.session_id || '?'
}

function polylineAttr(): string {
  return points
    .map((s, i) => `${xPos(i).toFixed(1)},${yPos(s.anomaly_score ?? 0).toFixed(1)}`)
    .join(' ')
}

const rotateLabels = points.length > 4
</script>

<template>
  <div class="anomaly-chart">
    <h4 class="chart-title">{{ t('chart.title') }}</h4>

    <div v-if="points.length < 2" class="chart-empty dim">
      {{ t('chart.no_data') }}
    </div>

    <svg
      v-else
      :viewBox="`0 0 ${W} ${H}`"
      class="chart-svg"
      role="img"
      aria-label="График anomaly_score по последним проверкам"
    >
      <!-- Y gridlines and labels -->
      <line
        v-for="g in [0, 0.5, 1]"
        :key="`grid-${g}`"
        :x1="PADDING_LEFT"
        :x2="W - PADDING_RIGHT"
        :y1="yPos(g)"
        :y2="yPos(g)"
        stroke="var(--border)"
        stroke-width="0.5"
        :stroke-dasharray="g === 0.5 ? 'none' : '3 3'"
      />
      <text
        v-for="g in [1, 0.5, 0]"
        :key="`ylab-${g}`"
        :x="PADDING_LEFT - 5"
        :y="yPos(g)"
        class="axis-label"
        text-anchor="end"
        dominant-baseline="middle"
      >
        {{ g.toFixed(2) }}
      </text>

      <!-- Threshold 0.5 (accent, dashed) -->
      <line
        :x1="PADDING_LEFT"
        :x2="W - PADDING_RIGHT"
        :y1="yPos(0.5)"
        :y2="yPos(0.5)"
        stroke="var(--accent)"
        stroke-width="1"
        stroke-dasharray="4 3"
        opacity="0.7"
      />

      <!-- History line -->
      <polyline
        :points="polylineAttr()"
        fill="none"
        stroke="var(--accent-dim)"
        stroke-width="1.5"
        stroke-linejoin="round"
        stroke-linecap="round"
      />

      <!-- Points, value labels, x labels -->
      <template v-for="(s, i) in points" :key="s.session_id">
        <circle
          :cx="xPos(i)"
          :cy="yPos(s.anomaly_score ?? 0)"
          r="4"
          :fill="statusColor(s.status)"
          stroke="var(--bg-panel)"
          stroke-width="1"
        />
        <text
          :x="xPos(i)"
          :y="yPos(s.anomaly_score ?? 0) - 9"
          class="value-label"
          text-anchor="middle"
        >
          {{ (s.anomaly_score ?? 0).toFixed(2) }}
        </text>
        <text
          :x="xPos(i)"
          :y="H - PADDING_BOTTOM + 14"
          class="axis-label"
          :text-anchor="rotateLabels ? 'end' : 'middle'"
          :transform="rotateLabels ? `rotate(-30 ${xPos(i)} ${H - PADDING_BOTTOM + 14})` : undefined"
        >
          {{ xLabel(s) }}
        </text>
      </template>
    </svg>

    <p class="chart-caption dim">{{ t('chart.caption') }}</p>
  </div>
</template>

<style scoped>
.anomaly-chart {
  margin-bottom: 12px;
}

.chart-title {
  font-size: 12px;
  font-weight: 600;
  margin: 0 0 6px;
  color: var(--text);
}

.chart-svg {
  width: 100%;
  height: auto;
  display: block;
}

.chart-empty {
  padding: 18px 8px;
  font-size: 12px;
  text-align: center;
  border: 1px dashed var(--border);
  border-radius: var(--radius);
}

.axis-label {
  font-size: 9px;
  fill: var(--text-dim);
}

.value-label {
  font-size: 9px;
  fill: var(--text);
  font-weight: 600;
}

.chart-caption {
  font-size: 10px;
  margin: 4px 0 0;
}
</style>
