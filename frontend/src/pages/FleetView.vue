<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { VehicleItem, FleetStats } from '../types'
import { getFleetStats, getFleetPriority, apiGet, apiUrl } from '../api'
import { t } from '../i18n'

const emit = defineEmits<{
  'open-vehicle': [id: string]
}>()

const stats = ref<FleetStats | null>(null)
const vehicles = ref<VehicleItem[]>([])
const priorityList = ref<VehicleItem[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

async function fetchData(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    await Promise.allSettled([
      fetchStats(),
      fetchPriority(),
      fetchAllVehicles(),
    ])
  } finally {
    loading.value = false
  }
}

async function fetchStats(): Promise<void> {
  try {
    stats.value = await getFleetStats()
  } catch (e) {
    if (e instanceof Error) error.value = e.message
  }
}

async function fetchPriority(): Promise<void> {
  try {
    priorityList.value = await getFleetPriority()
  } catch (e) {
    if (e instanceof Error) error.value = e.message
  }
}

async function fetchAllVehicles(): Promise<void> {
  try {
    vehicles.value = await apiGet<VehicleItem[]>(apiUrl('/api/vehicles'))
  } catch (e) {
    if (e instanceof Error) error.value = e.message
  }
}

onMounted(fetchData)

function groupClass(group: VehicleItem['group']): string {
  switch (group) {
    case 'normal': return 'badge-ok'
    case 'attention': return 'badge-warning'
    case 'quarantine': return 'badge-danger'
    default: return ''
  }
}

function groupLabel(group: VehicleItem['group']): string {
  switch (group) {
    case 'normal': return t('fleet.group.normal')
    case 'attention': return t('fleet.group.attention')
    case 'quarantine': return t('fleet.group.quarantine')
    default: return ''
  }
}

function statusBadgeClass(status: VehicleItem['latest_status']): string {
  switch (status) {
    case 'normal': return 'badge-ok'
    case 'anomaly': return 'badge-warning'
    case 'check_failed': return 'badge-danger'
    default: return ''
  }
}

function statusLabel(status: VehicleItem['latest_status']): string {
  switch (status) {
    case 'normal': return t('status.label.normal')
    case 'anomaly': return t('status.label.anomaly')
    case 'check_failed': return t('status.label.check_failed')
    default: return '—'
  }
}

function formatShortDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z')
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

function openVehicle(id: string): void {
  emit('open-vehicle', id)
}
</script>

<template>
  <div class="fleet-view">
    <!-- Error strip -->
    <div v-if="error" class="error-strip">
      {{ error }}
      <button class="retry-btn" @click="fetchData()">{{ t('fleet.retry') }}</button>
    </div>

    <!-- Loading skeletons -->
    <template v-if="loading">
      <div class="group-cards">
        <div v-for="i in 3" :key="i" class="skeleton-card panel">
          <div class="skeleton-line skeleton-line-lg"></div>
          <div class="skeleton-line skeleton-line-md"></div>
        </div>
      </div>
      <div class="skeleton-table panel">
        <div v-for="j in 4" :key="j" class="skeleton-line skeleton-line-md"></div>
      </div>
    </template>

    <!-- Data -->
    <template v-else>
      <!-- Group cards row -->
      <section class="group-cards">
        <div class="group-card card" :class="{ 'card-normal': true }">
          <span class="group-label dim">{{ t('fleet.group.normal') }}</span>
          <span class="group-num accent">{{ stats?.normal ?? 0 }}</span>
        </div>
        <div class="group-card card" :class="{ 'card-warning': true }">
          <span class="group-label dim">{{ t('fleet.requires_attention') }}</span>
          <span class="group-num warning">{{ stats?.attention ?? 0 }}</span>
        </div>
        <div class="group-card card" :class="{ 'card-danger': true }">
          <span class="group-label dim">{{ t('fleet.group.quarantine') }}</span>
          <span class="group-num danger">{{ stats?.quarantine ?? 0 }}</span>
        </div>
      </section>

      <!-- Priority list (quarantine vehicles) -->
      <section v-if="priorityList.length > 0" class="priority-section">
        <h3 class="section-title">{{ t('fleet.priority_list') }}</h3>
        <div class="priority-list">
          <div
            v-for="v in priorityList" :key="v.vehicle_id"
            class="priority-item card"
          >
            <div class="priority-row">
              <span class="mono garage-no">{{ v.garage_no }}</span>
              <span class="vehicle-id mono">{{ v.vehicle_id }}</span>
              <span v-if="v.engine_model" class="chip engine-chip">{{ v.engine_model }}</span>
              <span :class="['badge', groupClass(v.group)]">{{ groupLabel(v.group) }}</span>
            </div>
            <div class="priority-detail">
              <span v-if="v.latest_anomaly_title" class="anomaly-text">{{ v.latest_anomaly_title }}</span>
              <span v-else class="dim">{{ t('fleet.no_anomalies') }}</span>
            </div>
            <div class="priority-meta">
              <span :class="['badge', statusBadgeClass(v.latest_status)]">{{ statusLabel(v.latest_status) }}</span>
              <span v-if="v.latest_anomaly_score !== null" :class="['score-badge', 'badge-danger']">
                {{ v.latest_anomaly_score.toFixed(2) }}
              </span>
              <span class="dim mono date">{{ formatShortDate(v.latest_checked_at) }}</span>
              <button class="open-btn primary" @click="openVehicle(v.vehicle_id)">{{ t('fleet.open') }}</button>
            </div>
          </div>
        </div>
      </section>

      <!-- Full fleet table (collapsible) -->
      <details class="fleet-details">
        <summary class="fleet-summary">{{ t('fleet.all_fleet', { n: vehicles.length }) }}</summary>
        <div class="fleet-table-wrap">
          <table class="fleet-table">
            <thead>
              <tr>
                <th>{{ t('fleet.table.garage_no') }}</th>
                <th>{{ t('fleet.table.vehicle_id') }}</th>
                <th>{{ t('fleet.table.make_model') }}</th>
                <th>{{ t('fleet.table.engine') }}</th>
                <th>{{ t('fleet.table.group') }}</th>
                <th>{{ t('fleet.table.status') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="v in vehicles" :key="v.vehicle_id">
                <td class="mono">{{ v.garage_no }}</td>
                <td class="mono dim">{{ v.vehicle_id.slice(0, 8) }}…</td>
                <td>{{ v.make }} {{ v.model || '' }}</td>
                <td class="chip engine-sm">{{ v.engine_model }}</td>
                <td><span :class="['badge', groupClass(v.group)]">{{ groupLabel(v.group) }}</span></td>
                <td><span :class="['badge', statusBadgeClass(v.latest_status)]">{{ statusLabel(v.latest_status) }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </template>
  </div>
</template>

<style scoped>
.fleet-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Group cards — horizontal scroll on mobile */
.group-cards {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 4px;
}

@media (min-width: 640px) {
  .group-cards {
    flex-wrap: nowrap;
  }
}

.group-card {
  flex: 1;
  min-width: 140px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 16px 12px;
  text-align: center;
}

.card-normal {
  border-color: var(--accent-dim);
}

.card-warning {
  border-color: rgba(240, 166, 54, 0.3);
}

.card-danger {
  border-color: var(--danger);
}

.group-label {
  font-size: 12px;
}

.group-num {
  font-size: 32px;
  font-weight: 700;
  font-family: Consolas, monospace;
}

.group-num.accent { color: var(--accent); }
.group-num.warning { color: #f0a636; }
.group-num.danger { color: var(--danger-text); }

/* Priority section */
.section-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--text-dim);
}

.priority-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.priority-item {
  padding: 10px 12px;
  border-color: var(--border);
}

.priority-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.garage-no {
  font-size: 14px;
  font-weight: 700;
}

.vehicle-id {
  font-size: 12px;
  color: var(--text-dim);
}

.engine-chip {
  background: var(--bg-input);
  border: 1px solid var(--border);
  font-size: 11px;
}

.priority-detail {
  margin-bottom: 4px;
}

.anomaly-text {
  font-size: 13px;
  color: var(--text);
}

.priority-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.score-badge {
  background: var(--danger-bg);
  color: var(--danger-text);
  font-weight: 700;
}

.date {
  font-size: 11px;
}

.open-btn {
  margin-left: auto;
  padding: 4px 12px;
  font-size: 12px;
}

/* Full fleet table */
.fleet-details {
  border-top: 1px solid var(--border);
  padding-top: 8px;
}

.fleet-summary {
  cursor: pointer;
  font-size: 13px;
  color: var(--text-dim);
  padding: 4px 0;
  user-select: none;
}

.fleet-summary:hover {
  color: var(--text);
}

.fleet-table-wrap {
  overflow-x: auto;
  margin-top: 8px;
}

.fleet-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  white-space: nowrap;
}

.fleet-table th {
  text-align: left;
  padding: 6px 8px;
  color: var(--text-dim);
  font-weight: 600;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  background: var(--bg-panel);
}

.fleet-table td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}

.engine-sm {
  font-size: 11px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  padding: 1px 6px;
  border-radius: 4px;
  color: var(--text-dim);
}

/* Skeleton loading */
.skeleton-card {
  min-height: 72px;
}

.skeleton-table {
  min-height: 120px;
}

.skeleton-line {
  background: linear-gradient(90deg, var(--bg-input) 25%, var(--border) 50%, var(--bg-input) 75%);
  background-size: 200% 100%;
  animation: skeleton-pulse 1.5s ease-in-out infinite;
  border-radius: var(--radius-sm);
}

.skeleton-line-lg {
  height: 24px;
  width: 60%;
  margin-bottom: 8px;
}

.skeleton-line-md {
  height: 14px;
  width: 80%;
  margin-bottom: 6px;
}

.retry-btn {
  margin-left: 12px;
  padding: 2px 10px;
  font-size: 12px;
  min-height: auto;
  background: var(--danger-bg);
  color: var(--danger-text);
}

@keyframes skeleton-pulse {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>
