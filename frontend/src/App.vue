<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
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

// Backend liveness for the topbar status dot (unauthenticated /health probe).
const backendUp = ref(true)
let healthTimer: ReturnType<typeof setInterval> | null = null

async function pingHealth(): Promise<void> {
  try {
    const r = await fetch(apiUrl('/health'))
    backendUp.value = r.ok
  } catch {
    backendUp.value = false
  }
}

onMounted(() => {
  void pingHealth()
  healthTimer = setInterval(() => { void pingHealth() }, 60_000)
})

onBeforeUnmount(() => {
  if (healthTimer) clearInterval(healthTimer)
  healthTimer = null
})

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
        <span
          class="status-dot"
          role="img"
          :class="{ down: !backendUp }"
          :title="backendUp ? t('app.status.online') : t('app.status.offline')"
          :aria-label="backendUp ? t('app.status.online') : t('app.status.offline')"
        />
      </div>

      <nav class="topbar-nav">
        <button :class="['nav-btn', { active: page === 'garage' }]" @click="page = 'garage'">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9L18 10l-2.7-3.6A1.5 1.5 0 0 0 14 6H8a2 2 0 0 0-1.8 1.1L4 10l-2.5.6A1.5 1.5 0 0 0 0 12.1V16c0 .6.4 1 1 1h2"/>
            <circle cx="7" cy="17" r="2"/>
            <path d="M9 17h6"/>
            <circle cx="17" cy="17" r="2"/>
          </svg>
          {{ t('app.nav.garage') }}
        </button>
        <button :class="['nav-btn', { active: page === 'chat' }]" @click="page = 'chat'">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          {{ t('app.nav.chat') }}
        </button>
        <button :class="['nav-btn', { active: page === 'fleet' }]" @click="page = 'fleet'">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2"/>
            <path d="M15 18H9"/>
            <path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.62l-3.48-4.35A1 1 0 0 0 17.52 8H14"/>
            <circle cx="17" cy="18" r="2"/>
            <circle cx="7" cy="18" r="2"/>
          </svg>
          {{ t('app.nav.fleet') }}
        </button>
        <button
          v-if="auth.role.value === 'admin'"
          :class="['nav-btn', { active: page === 'admin' }]"
          @click="page = 'admin'"
        >
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>
          </svg>
          {{ t('app.nav.admin') }}
        </button>
      </nav>

      <div class="topbar-foot">
        <LocaleSwitcher />
        <div class="topbar-user">
          <span class="username">{{ auth.username.value }}</span>
          <span class="role-chip">{{ auth.role.value === 'admin' ? t('app.role.admin') : t('app.role.user') }}</span>
          <button class="logout-btn" @click="handleLogout">{{ t('app.logout') }}</button>
        </div>
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
  display: flex;
  align-items: center;
  gap: 8px;
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

.status-dot {
  display: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  flex-shrink: 0;
}

.status-dot.down {
  background: var(--danger);
}

.nav-icon {
  display: none;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.topbar-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
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
    padding: 10px 12px;
  }

  .topbar-brand {
    justify-content: space-between;
  }

  .brand-title {
    font-size: 16px;
  }

  .status-dot {
    display: inline-block;
  }

  .topbar-nav {
    gap: 8px;
  }

  .nav-btn {
    flex: 1;
    justify-content: center;
    border: 1px solid var(--border);
    background: var(--bg-input);
    min-height: 38px;
    padding: 6px 4px;
    font-size: 12px;
  }

  .nav-btn.active {
    background: var(--accent-dim);
    color: var(--text-on-accent);
    border-color: var(--accent);
  }

  .nav-btn.active:hover:not(:disabled) {
    background: var(--accent-dim);
    color: var(--text-on-accent);
  }

  .nav-icon {
    display: block;
  }

  .topbar-foot {
    justify-content: space-between;
  }
}
</style>
