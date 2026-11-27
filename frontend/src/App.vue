<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { VehicleItem, FleetStats } from './types'
import { auth } from './composables/useAuth'
import { apiUrl } from './api'
import { t } from './i18n'
import LocaleSwitcher from './components/LocaleSwitcher.vue'
import LoginView from './pages/LoginView.vue'
import GarageView from './pages/GarageView.vue'
import ChatView from './pages/ChatView.vue'
import FleetView from './pages/FleetView.vue'
import AdminView from './pages/AdminView.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import ChangePasswordModal from './components/ChangePasswordModal.vue'

type Page = 'login' | 'garage' | 'chat' | 'fleet' | 'admin'
const page = ref<Page>('login')

// Splash guard — prevents flash of LoginView during auth restore on hard reload.
const restoring = ref(true)

// Auth state
const loginError = ref<string | null>(null)
const pwdChangeError = ref<string | null>(null)
const pwdChangeLoading = ref(false)

// Garage data
const vehicles = ref<VehicleItem[]>([])
const fleetStats = ref<FleetStats | null>(null)
const garageLoading = ref(false)
const searchQuery = ref('')
const groupFilter = ref<'all' | 'normal' | 'attention' | 'quarantine'>('all')

// Current vehicle (for chat navigation)
let currentVehicleId = ''

async function restoreAuth(): Promise<void> {
  const ok = await auth.restore()
  restoring.value = false
  page.value = ok ? 'garage' : 'login'
  if (ok && !auth.mustChangePassword.value) fetchGarageData()
}

async function handleLogin(username: string, password: string): Promise<void> {
  loginError.value = null
  try {
    await auth.login(username, password)
    page.value = 'garage'
    fetchGarageData()
  } catch (e) {
    if (e instanceof Error) {
      loginError.value = e.message || t('login.error.password')
    } else {
      loginError.value = t('login.error.password')
    }
  }
}

async function handlePasswordChange(oldP: string, newP: string): Promise<void> {
  pwdChangeError.value = null
  pwdChangeLoading.value = true
  try {
    await auth.changePassword(oldP, newP)
    fetchGarageData()
  } catch (e) {
    if (e instanceof Error) {
      pwdChangeError.value = e.message || t('login.error.change')
    } else {
      pwdChangeError.value = t('login.error.change')
    }
  } finally {
    pwdChangeLoading.value = false
  }
}

function handleLogout(): void {
  auth.logout()
  page.value = 'login'
  vehicles.value = []
  fleetStats.value = null
  searchQuery.value = ''
  groupFilter.value = 'all'
}

// Garage data fetching
async function fetchGarageData(): Promise<void> {
  garageLoading.value = true
  try {
    await Promise.all([fetchVehicles(), fetchFleetStats()])
  } catch {
    // If token expired, logout and redirect
    handleLogout()
  } finally {
    garageLoading.value = false
  }
}

async function fetchVehicles(): Promise<void> {
  // We'll use a simple GET with query params; the parent component handles filtering.
  const params = new URLSearchParams()
  if (searchQuery.value) params.set('query', searchQuery.value)
  if (groupFilter.value !== 'all') params.set('group', groupFilter.value)
  const query = params.toString()
  const url = apiUrl('/api/vehicles') + (query ? `?${query}` : '')

  try {
    const data = await fetch(url, {
      headers: { Authorization: `Bearer ${auth.token.value}` },
    }).then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      return r.json()
    })
    vehicles.value = (data as VehicleItem[])
  } catch {
    // On error, keep existing data
  }
}

async function fetchFleetStats(): Promise<void> {
  try {
    const data = await fetch(apiUrl('/api/fleet/stats'), {
      headers: { Authorization: `Bearer ${auth.token.value}` },
    }).then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      return r.json()
    })
    fleetStats.value = data as FleetStats
  } catch {
    // Keep existing stats
  }
}

function handleVehicleClick(id: string): void {
  currentVehicleId = id
  page.value = 'chat'
}

// Debounced search/filter on garage data
let fetchTimer: ReturnType<typeof setTimeout> | null = null
function onSearchUpdate(query: string): void {
  searchQuery.value = query
  scheduleFetch()
}

function onFilterUpdate(group: 'all' | 'normal' | 'attention' | 'quarantine'): void {
  groupFilter.value = group
  scheduleFetch()
}

function scheduleFetch(): void {
  if (fetchTimer) clearTimeout(fetchTimer)
  fetchTimer = setTimeout(() => {
    fetchVehicles()
  }, 250)
}

onMounted(restoreAuth)
</script>

<template>
  <div class="app-root">
    <!-- Top bar (only when authenticated) -->
    <header v-if="page !== 'login'" class="topbar">
      <div class="topbar-brand">
        <span class="brand-title">{{ t('app.title') }}</span>
      </div>

      <nav class="topbar-nav">
        <button
          :class="['nav-btn', { active: page === 'garage' }]"
          @click="page = 'garage'"
        >
          {{ t('app.nav.garage') }}
        </button>
        <button
          :class="['nav-btn', { active: page === 'chat' }]"
          @click="page = 'chat'"
        >
          {{ t('app.nav.chat') }}
        </button>
        <button
          :class="['nav-btn', { active: page === 'fleet' }]"
          @click="page = 'fleet'"
        >
          {{ t('app.nav.fleet') }}
        </button>
        <button
          v-if="auth.role.value === 'admin'"
          :class="['nav-btn', { active: page === 'admin' }]"
          @click="page = 'admin'"
        >
          {{ t('app.nav.admin') }}
        </button>
      </nav>

      <LocaleSwitcher />

      <div class="topbar-user">
        <span class="username">{{ auth.username.value }}</span>
        <span class="role-chip">{{ auth.role.value === 'admin' ? t('app.role.admin') : t('app.role.user') }}</span>
        <button class="logout-btn" @click="handleLogout">{{ t('app.logout') }}</button>
      </div>
    </header>

    <!-- Splash screen while auth is being restored (prevents login flash) -->
    <div v-if="restoring" class="splash">
      <span class="spinner" />
    </div>

    <!-- Page content -->
    <main v-else class="main-content">
      <!-- Login page -->
      <LoginView
        v-if="page === 'login'"
        :error="loginError"
        @login="handleLogin"
        @dismissed-error="loginError = null"
      />

      <!-- Garage page -->
      <GarageView
        v-else-if="page === 'garage'"
        :vehicles="vehicles"
        :stats="fleetStats"
        :loading="garageLoading"
        @open-vehicle="handleVehicleClick"
        @update-search="onSearchUpdate"
        @update-filter="onFilterUpdate"
      />

      <!-- Chat page -->
      <ChatView
        v-else-if="page === 'chat'"
        :vehicle-id="currentVehicleId"
        @back="() => { page = 'garage'; fetchGarageData() }"
      />

      <!-- Fleet page (all users) -->
      <FleetView
        v-else-if="page === 'fleet'"
        @open-vehicle="(id: string) => { currentVehicleId = id; page = 'chat' }"
      />

      <!-- Admin page (admin only) -->
      <AdminView
        v-else-if="page === 'admin'"
      />

      <!-- Stub fallback -->
      <div v-else class="stub-page panel">
        <h2>{{ t('app.stub.title', { page }) }}</h2>
        <p class="dim">{{ t('app.stub.body') }}</p>
      </div>
    </main>

    <!-- Confirm dialog (for future use) -->
    <ConfirmDialog />

    <!-- Mandatory password-change modal -->
    <ChangePasswordModal
      v-if="auth.mustChangePassword.value"
      :error="pwdChangeError"
      :loading="pwdChangeLoading"
      @submit="handlePasswordChange"
    />
  </div>
</template>

<style scoped>
.app-root {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

/* Top bar */
.topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}

.topbar-brand {
  flex-shrink: 0;
}

.brand-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: 0.02em;
}

.topbar-nav {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  flex: 1;
}

.nav-btn {
  background: transparent;
  border: 0;
  border-radius: var(--radius);
  padding: 6px 12px;
  font-size: 13px;
  color: var(--text-dim);
  cursor: pointer;
  white-space: nowrap;
  min-height: 40px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.nav-btn:hover:not(:disabled) {
  background: var(--bg-input);
  color: var(--text);
}

.nav-btn.active {
  background: var(--bg-input);
  color: var(--accent);
}

.soon-hint {
  font-size: 10px;
  color: var(--text-dim);
  opacity: 0.6;
}

.topbar-user {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.username {
  font-size: 13px;
  color: var(--text);
}

.role-chip {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--bg-input);
  color: var(--text-dim);
}

.logout-btn {
  background: transparent;
  border: 0;
  color: var(--danger);
  font-size: 13px;
  padding: 6px 10px;
  cursor: pointer;
  min-height: 40px;
}

.logout-btn:hover {
  color: var(--danger-text);
}

.main-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 16px;
}

.splash {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
}

.stub-page {
  max-width: 480px;
  margin: 48px auto;
  text-align: center;
}

@media (max-width: 640px) {
  .topbar {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }

  .topbar-nav {
    justify-content: space-between;
  }

  .nav-btn {
    font-size: 12px;
    padding: 6px 8px;
  }

  .topbar-user {
    justify-content: space-between;
  }
}
</style>
