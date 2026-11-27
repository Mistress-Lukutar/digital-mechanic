<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { VehicleItem, FleetStats, VehicleGroup } from '../types'
import { apiGet, apiUrl, formatIso } from '../api'
import { t } from '../i18n'

interface ConfigCheckItem {
  check: string
  ok: boolean
  detail: string
  hint: string
}

interface ConfigStatusResponse {
  overall: boolean
  checks: ConfigCheckItem[]
}

defineProps<{
  vehicles: VehicleItem[]
  stats: FleetStats | null
  loading: boolean
}>()

const emit = defineEmits<{
  'open-vehicle': [id: string]
  'update-search': [query: string]
  'update-filter': [group: 'all' | VehicleGroup]
}>()

// Search + debounce
const searchQuery = ref('')
let searchTimer: ReturnType<typeof setTimeout> | null = null

function onSearchInput(): void {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    // Parent watches the query prop — we emit a debounced update.
    emit('update-search', searchQuery.value.trim())
  }, 250)
}

// Filter chips
type GroupFilter = 'all' | VehicleGroup
const activeFilter = ref<GroupFilter>('all')

function setFilter(group: GroupFilter): void {
  activeFilter.value = group
  emit('update-filter', group)
}

// Status badge helpers
function statusLabel(status: VehicleItem['latest_status']): string {
  switch (status) {
    case 'normal': return t('status.label.normal')
    case 'anomaly': return t('status.label.anomaly')
    case 'check_failed': return t('status.label.check_failed')
    default: return '—'
  }
}

function groupClass(group: VehicleItem['group']): string {
  switch (group) {
    case 'normal': return 'badge-ok'
    case 'attention': return 'badge-warning'
    case 'quarantine': return 'badge-danger'
    default: return ''
  }
}

// Skeleton row count for loading state
const skeletonCount = Array.from({ length: 6 }, (_, i) => i)

// Config-status warning banner (session-scoped, local ref only).
const showConfigWarning = ref(false)

let _lastChecks: ConfigCheckItem[] = []

function getFailedChecks(): ConfigCheckItem[] {
  return _lastChecks.filter((c: ConfigCheckItem) => !c.ok)
}

onMounted(async (): Promise<void> => {
  try {
    const data = await apiGet<ConfigStatusResponse>(apiUrl('/api/config-status'))
    if (!data.overall && Array.isArray(data.checks)) {
      _lastChecks = data.checks
      showConfigWarning.value = true
    }
  } catch {
    // Fetch failure → silently ignore, no banner.
  }
})
</script>

<template>
  <div class="garage-page">
    <!-- Config-status warning banner -->
    <div v-if="showConfigWarning" class="config-warning-strip panel">
      <strong>{{ t('config.warning_title') }}</strong>
      <span
        v-for="c in (getFailedChecks() as { check: string; ok: boolean; detail: string; hint: string }[])"
        :key="c.check"
        class="warning-line"
      >{{ c.check }} — {{ c.detail }}. {{ c.hint }}</span>
      <button
        class="dismiss-btn"
        :aria-label="t('config.dismiss')"
        title="Скрыть"
        @click="showConfigWarning = false"
      >×</button>
    </div>

    <!-- Search + filter bar -->
    <div class="search-row">
      <input
        v-model="searchQuery"
        type="text"
        :placeholder="t('garage.search.placeholder')"
        class="search-input"
        @input="onSearchInput"
      />

      <div class="filter-chips">
        <button
          :class="['chip', { active: activeFilter === 'all' }]"
          @click="setFilter('all')"
        >
          {{ t('garage.filter.all') }}
          <span v-if="stats?.total" class="chip-count">{{ stats.total }}</span>
        </button>
        <button
          :class="['chip', { active: activeFilter === 'normal' }]"
          @click="setFilter('normal')"
        >
          {{ t('garage.filter.normal') }}
          <span v-if="stats?.normal" class="chip-count">{{ stats.normal }}</span>
        </button>
        <button
          :class="['chip', { active: activeFilter === 'attention' }]"
          @click="setFilter('attention')"
        >
          {{ t('garage.filter.attention') }}
          <span v-if="stats?.attention" class="chip-count">{{ stats.attention }}</span>
        </button>
        <button
          :class="['chip', { active: activeFilter === 'quarantine' }]"
          @click="setFilter('quarantine')"
        >
          {{ t('garage.filter.quarantine') }}
          <span v-if="stats?.quarantine" class="chip-count">{{ stats.quarantine }}</span>
        </button>
      </div>
    </div>

    <!-- Vehicle cards grid -->
    <div v-if="loading" class="grid-cards">
      <div v-for="i in skeletonCount" :key="i" class="skeleton-card panel">
        <div class="skeleton-line skeleton-line-lg"></div>
        <div class="skeleton-line skeleton-line-md"></div>
        <div class="skeleton-row">
          <span class="skeleton-line skeleton-chip"></span>
          <span class="skeleton-line skeleton-chip"></span>
        </div>
        <div class="skeleton-line skeleton-line-sm"></div>
      </div>
    </div>

    <div v-else-if="vehicles.length === 0" class="empty-state">
      {{ t('garage.empty') }}
    </div>

    <div v-else class="grid-cards">
      <div
        v-for="v in vehicles" :key="v.vehicle_id"
        class="vehicle-card panel card"
        @click="emit('open-vehicle', v.vehicle_id)"
      >
        <div class="card-header">
          <div class="vehicle-info">
            <span class="vehicle-id">{{ v.garage_no }}</span>
            <span class="dim mono vehicle-plate">{{ t('garage.vehicle_id') }} {{ v.vehicle_id }}</span>
          </div>
          <span class="badge" :class="groupClass(v.group)">{{ statusLabel(v.latest_status) }}</span>
        </div>

        <div class="card-body">
          <p class="make-model">
            {{ v.make }} {{ v.model }}
          </p>
          <div class="chips-row">
            <span v-if="v.engine_model" class="chip">{{ v.engine_model }}</span>
            <span v-if="v.fuel" class="chip">{{ v.fuel }}</span>
          </div>

          <div class="meta-row">
            <span v-if="v.latest_checked_at" class="dim mono">
              {{ formatIso(v.latest_checked_at) }}
            </span>
          </div>

          <div class="counts-row">
            <span class="count-line">
              {{ t('garage.counts_anomalies', { n: v.anomaly_count }) }} &nbsp;|&nbsp; {{ t('garage.counts_checks', { m: v.check_count }) }}
            </span>
          </div>

          <p v-if="v.latest_anomaly_title" class="anomaly-title error-text">
            {{ v.latest_anomaly_title }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.garage-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.search-row {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

@media (min-width: 640px) {
  .search-row {
    flex-direction: row;
    align-items: center;
  }
}

.search-input {
  flex: 1;
  min-width: 0;
  padding: 8px 12px;
  font-size: 14px;
  border-radius: var(--radius);
  background: var(--bg-input);
  color: var(--text);
  border: 1px solid var(--border);
}

.search-input:focus {
  outline: none;
  border-color: var(--accent);
}

.filter-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip-count {
  margin-left: 4px;
  color: var(--text-dim);
  font-size: 11px;
}

.grid-cards {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}

@media (min-width: 640px) {
  .grid-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (min-width: 1024px) {
  .grid-cards {
    grid-template-columns: repeat(3, 1fr);
  }
}

/* Vehicle card */
.card {
  border: 1px solid var(--border);
  transition: border-color 0.15s;
  cursor: pointer;
}

.card:hover {
  border-color: var(--accent-dim);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.vehicle-id {
  font-size: 16px;
  font-weight: 700;
  font-family: Consolas, monospace;
  letter-spacing: 0.02em;
}

.vehicle-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.vehicle-plate {
  font-size: 11px;
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.make-model {
  margin: 0;
  font-size: 14px;
  color: var(--text);
}

.chips-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.meta-row {
  margin-top: 8px;
}

.counts-row {
  margin-top: 6px;
}

.count-line {
  font-size: 12px;
  color: var(--text-dim);
}

.anomaly-title {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 1.4;
}

/* Empty state */
.empty-state {
  text-align: center;
  padding: 48px 16px;
  color: var(--text-dim);
  font-size: 15px;
}

/* Skeleton loading */
.skeleton-card {
  min-height: 120px;
}

.skeleton-line {
  background: linear-gradient(90deg, var(--bg-input) 25%, var(--border) 50%, var(--bg-input) 75%);
  background-size: 200% 100%;
  animation: skeleton-pulse 1.5s ease-in-out infinite;
  border-radius: var(--radius-sm);
}

.skeleton-line-lg {
  height: 18px;
  width: 60%;
  margin-bottom: 10px;
}

.skeleton-line-md {
  height: 14px;
  width: 80%;
  margin-bottom: 8px;
}

.skeleton-line-sm {
  height: 12px;
  width: 40%;
}

.skeleton-chip {
  height: 16px;
  width: 70px;
  border-radius: 999px;
}

.skeleton-row {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

@keyframes skeleton-pulse {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* Config warning strip */
.config-warning-strip {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 14px;
  background: #3b2e0a;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: #f5c542;
}

.config-warning-strip strong {
  font-size: 14px;
}

.warning-line {
  font-size: 13px;
  line-height: 1.4;
  color: #e0b830;
}

.dismiss-btn {
  align-self: flex-end;
  background: none;
  border: none;
  color: #f5c542;
  font-size: 18px;
  cursor: pointer;
  padding: 2px 6px;
  line-height: 1;
}

.dismiss-btn:hover {
  color: #fff;
}
</style>
