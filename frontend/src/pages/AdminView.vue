<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { UsageTotals, UsageRowItem, AdminUserItem, LlmSettingsView } from '../types'
import { getAdminUsageTotals, getAdminUsageRecent, getAdminUsers, createAdminUser, deleteAdminUser, resetAdminPassword, getLlmSettings, updateLlmSettings } from '../api'
import { useConfirm } from '../composables/useConfirm'

const { confirm } = useConfirm()

type TabKey = 'dashboard' | 'users' | 'llm'
const activeTab = ref<TabKey>('dashboard')

// Dashboard data
const usageTotals = ref<UsageTotals | null>(null)
const recentUsage = ref<UsageRowItem[]>([])
const loadingData = ref(false)
const errorStrip = ref<string | null>(null)

async function loadDashboard(): Promise<void> {
  loadingData.value = true
  errorStrip.value = null
  try {
    const [totals, recent] = await Promise.all([
      getAdminUsageTotals(),
      getAdminUsageRecent(50),
    ])
    usageTotals.value = totals
    recentUsage.value = recent
  } catch (e) {
    if (e instanceof Error) errorStrip.value = e.message
  } finally {
    loadingData.value = false
  }
}

// Users data
const users = ref<AdminUserItem[]>([])
const loadingUsers = ref(false)
const addUserOpen = ref(false)
const newUser = ref({ username: '', password: '', role: 'user' as string })
const userError = ref<string | null>(null)
const resettingPassword = ref<Record<string, boolean>>({})
const newPasswords = ref<Record<string, string>>({})

async function loadUsers(): Promise<void> {
  loadingUsers.value = true
  userError.value = null
  try {
    users.value = await getAdminUsers()
  } catch (e) {
    if (e instanceof Error) userError.value = e.message
  } finally {
    loadingUsers.value = false
  }
}

async function handleCreateUser(): Promise<void> {
  userError.value = null
  try {
    await createAdminUser(newUser.value.username, newUser.value.password, newUser.value.role)
    addUserOpen.value = false
    newUser.value = { username: '', password: '', role: 'user' }
    await loadUsers()
  } catch (e) {
    if (e instanceof Error) userError.value = e.message
  }
}

async function handleDeleteUser(username: string): Promise<void> {
  const ok = await confirm({
    title: 'Удалить пользователя',
    message: `Удалить «${username}»?`,
    confirmLabel: 'Удалить',
    danger: true,
  })
  if (!ok) return
  userError.value = null
  try {
    await deleteAdminUser(username)
    await loadUsers()
  } catch (e) {
    if (e instanceof Error) userError.value = e.message
  }
}

async function handleResetPassword(username: string): Promise<void> {
  const pw = newPasswords.value[username]
  if (!pw || pw.length < 8) {
    userError.value = 'Пароль должен содержать минимум 8 символов'
    return
  }
  resettingPassword.value[username] = true
  try {
    await resetAdminPassword(username, pw)
    delete newPasswords.value[username]
    delete resettingPassword.value[username]
  } catch (e) {
    if (e instanceof Error) userError.value = e.message
  } finally {
    resettingPassword.value[username] = false
  }
}

// LLM settings
const llmSettings = ref<LlmSettingsView | null>(null)
const loadingLlm = ref(false)
const savingLlm = ref(false)
const llmError = ref<string | null>(null)
const llmForm = ref({
  protocol: 'openai_compatible',
  base_url: '',
  api_key: '',
  model: '',
  temperature: 0.7,
  max_output_tokens: null as number | null,
})

async function loadLlmSettings(): Promise<void> {
  loadingLlm.value = true
  llmError.value = null
  try {
    const settings = await getLlmSettings()
    llmSettings.value = settings
    // Populate form (don't overwrite api_key if user hasn't typed)
    llmForm.value.protocol = settings.protocol || 'openai_compatible'
    llmForm.value.base_url = settings.base_url || ''
    llmForm.value.model = settings.model || ''
    llmForm.value.temperature = settings.temperature ?? 0.7
    llmForm.value.max_output_tokens = settings.max_output_tokens ?? null
    llmForm.value.api_key = '' // empty means keep current
  } catch (e) {
    if (e instanceof Error) llmError.value = e.message
  } finally {
    loadingLlm.value = false
  }
}

async function handleSaveLlm(): Promise<void> {
  savingLlm.value = true
  llmError.value = null
  try {
    const result = await updateLlmSettings({
      protocol: llmForm.value.protocol || undefined,
      base_url: llmForm.value.base_url || undefined,
      api_key: llmForm.value.api_key || undefined,
      model: llmForm.value.model || undefined,
      temperature: llmForm.value.temperature,
      max_output_tokens: llmForm.value.max_output_tokens,
    })
    llmSettings.value = result
    // Refresh masked api_key display
    llmForm.value.api_key = ''
  } catch (e) {
    if (e instanceof Error) llmError.value = e.message
  } finally {
    savingLlm.value = false
  }
}

onMounted(() => {
  loadDashboard()
  loadUsers()
  loadLlmSettings()
})

function formatIso(value: string): string {
  if (!value) return '—'
  const iso = value.endsWith('Z') || value.includes('+') ? value : value + 'Z'
  const d = new Date(iso)
  return isNaN(d.getTime()) ? value : d.toLocaleString('ru-RU', { hour12: false })
}

function kindChipClass(kind: string): string {
  if (kind === 'chat') return 'badge-ok'
  if (kind.includes('error')) return 'badge-danger'
  return ''
}
</script>

<template>
  <div class="admin-view">
    <!-- Tab buttons -->
    <div class="tab-bar">
      <button
        :class="['chip', { active: activeTab === 'dashboard' }]"
        @click="activeTab = 'dashboard'"
      >Дашборд</button>
      <button
        :class="['chip', { active: activeTab === 'users' }]"
        @click="activeTab = 'users'"
      >Пользователи</button>
      <button
        :class="['chip', { active: activeTab === 'llm' }]"
        @click="activeTab = 'llm'"
      >Настройки LLM</button>
    </div>

    <!-- Dashboard tab -->
    <section v-if="activeTab === 'dashboard'" class="tab-content">
      <h3>Дашборд использования</h3>

      <!-- 4 stat cards -->
      <div class="stat-cards">
        <div class="stat-card panel">
          <span class="stat-label dim">Запросов</span>
          <span class="stat-num">{{ usageTotals?.requests_total ?? '—' }}</span>
        </div>
        <div class="stat-card panel">
          <span class="stat-label dim">Ошибок</span>
          <span class="stat-num stat-error">{{ usageTotals?.requests_error ?? '—' }}</span>
        </div>
        <div class="stat-card panel">
          <span class="stat-label dim">Входящие токены</span>
          <span class="stat-num">{{ usageTotals?.input_tokens ?? '—' }}</span>
        </div>
        <div class="stat-card panel">
          <span class="stat-label dim">Исходящие токены</span>
          <span class="stat-num">{{ usageTotals?.output_tokens ?? '—' }}</span>
        </div>
      </div>

      <!-- Recent requests table -->
      <h4 class="section-title">Последние запросы</h4>
      <div class="table-actions">
        <button :disabled="loadingData" @click="loadDashboard()">Обновить</button>
      </div>

      <div v-if="errorStrip" class="error-strip">{{ errorStrip }}</div>

      <div v-if="loadingData" class="dim">Загрузка…</div>

      <div v-else class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Время</th>
              <th>Пользователь</th>
              <th>Тип</th>
              <th>Модель</th>
              <th>ID ТС</th>
              <th>Вх. токены</th>
              <th>Исх. токены</th>
              <th>Длительность (мс)</th>
              <th>Статус</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in recentUsage" :key="r.id">
              <td class="mono">{{ formatIso(r.ts) }}</td>
              <td>{{ r.username || '—' }}</td>
              <td><span :class="['chip', kindChipClass(r.kind)]">{{ r.kind }}</span></td>
              <td class="dim mono">{{ r.model || '—' }}</td>
              <td class="mono dim">{{ r.vehicle_id || '—' }}</td>
              <td class="mono">{{ r.input_tokens }}</td>
              <td class="mono">{{ r.output_tokens }}</td>
              <td class="mono">{{ r.duration_ms }}</td>
              <td>
                <span v-if="r.status === 'ok'" class="badge badge-ok">OK</span>
                <span v-else class="badge badge-danger" :title="r.error || ''">Ошибка</span>
              </td>
            </tr>
          </tbody>
        </table>

        <div v-if="recentUsage.length === 0" class="dim" style="padding: 16px; text-align: center;">
          Записей нет
        </div>
      </div>
    </section>

    <!-- Users tab -->
    <section v-if="activeTab === 'users'" class="tab-content">
      <h3>Пользователи</h3>

      <!-- Add user form -->
      <details :open="addUserOpen" @toggle="addUserOpen = ($event.target as HTMLDetailsElement).open">
        <summary class="add-user-summary">Добавить пользователя</summary>
        <form class="add-user-form" @submit.prevent="handleCreateUser">
          <div class="field-row">
            <input v-model="newUser.username" placeholder="Имя пользователя" required />
            <input v-model="newUser.password" type="password" placeholder="Пароль (мин. 8)" required minlength="8" autocomplete="new-password" />
            <select v-model="newUser.role">
              <option value="user">пользователь</option>
              <option value="admin">админ</option>
            </select>
            <button type="submit" class="primary">Создать</button>
          </div>
        </form>
      </details>

      <!-- Error strip -->
      <div v-if="userError" class="error-strip">{{ userError }}</div>

      <!-- Users table -->
      <div v-if="loadingUsers" class="dim">Загрузка…</div>
      <template v-else>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Имя</th>
                <th>Роль</th>
                <th>Смена пароля</th>
                <th>Дата создания</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in users" :key="u.username">
                <td class="mono">{{ u.username }}</td>
                <td><span :class="['chip', u.role === 'admin' ? '' : 'badge-ok']">{{ u.role }}</span></td>
                <td>
                  <span v-if="u.must_change_password" class="badge badge-warning">сменит пароль</span>
                  <span v-else class="dim">—</span>
                </td>
                <td class="mono dim">{{ formatIso(u.created_at) }}</td>
                <td class="actions-cell">
                  <!-- Reset password: inline form -->
                  <template v-if="resettingPassword[u.username]">
                    <input
                      v-model="newPasswords[u.username]"
                      type="password"
                      placeholder="Новый пароль"
                      autocomplete="new-password"
                      style="width: 120px; padding: 3px 6px;"
                      @keydown.enter="handleResetPassword(u.username)"
                    />
                    <button :disabled="!newPasswords[u.username]" class="primary" style="padding: 2px 8px; font-size: 12px; min-height: auto;" @click="handleResetPassword(u.username)">
                      {{ resettingPassword[u.username] ? '…' : 'OK' }}
                    </button>
                  </template>
                  <template v-else>
                    <button style="padding: 2px 8px; font-size: 12px; min-height: auto;" @click="newPasswords[u.username] = ''; resettingPassword[u.username] = true">Сбросить пароль</button>
                  </template>
                  <button class="danger-solid" style="padding: 2px 8px; font-size: 12px; min-height: auto;" @click="handleDeleteUser(u.username)">Удалить</button>
                </td>
              </tr>
            </tbody>
          </table>

          <div v-if="users.length === 0" class="dim" style="padding: 16px; text-align: center;">
            Пользователей нет
          </div>
        </div>
      </template>
    </section>

    <!-- LLM settings tab -->
    <section v-if="activeTab === 'llm'" class="tab-content">
      <h3>Настройки LLM</h3>

      <div v-if="llmError" class="error-strip">{{ llmError }}</div>

      <form v-if="!loadingLlm && llmSettings" class="llm-form" @submit.prevent="handleSaveLlm">
        <div class="field">
          <label class="label">Протокол</label>
          <select v-model="llmForm.protocol">
            <option value="openai_compatible">openai_compatible</option>
            <option value="anthropic">anthropic</option>
            <option value="google_gemini">google_gemini</option>
          </select>
        </div>

        <div class="field">
          <label class="label">Base URL</label>
          <input v-model="llmForm.base_url" type="url" placeholder="https://api.example.com/v1" />
        </div>

        <div class="field">
          <label class="label">API ключ</label>
          <input
            v-model="llmForm.api_key"
            type="password"
            autocomplete="off"
            :placeholder="llmSettings.api_key || 'не задан'"
          />
          <span class="field-hint dim">Ключ хранится на сервере и не возвращается в открытом виде</span>
        </div>

        <div class="field">
          <label class="label">Модель</label>
          <input v-model="llmForm.model" type="text" placeholder="model-name" />
        </div>

        <div class="field">
          <label class="label">Temperature (0–1)</label>
          <input v-model.number="llmForm.temperature" type="number" min="0" max="1" step="0.1" />
        </div>

        <div class="field">
          <label class="label">Max output tokens</label>
          <input v-model.number="llmForm.max_output_tokens" type="number" placeholder="пусто = без лимита" />
        </div>

        <div class="form-actions">
          <button type="submit" :disabled="savingLlm" class="primary">Сохранить</button>
          <span v-if="savingLlm" class="dim">Сохранение…</span>
        </div>
      </form>

      <!-- Saved state display -->
      <div v-if="llmSettings && !savingLlm" class="llm-saved panel">
        <h4>Текущие настройки</h4>
        <dl class="kv-grid">
          <dt>Протокол</dt><dd>{{ llmSettings.protocol }}</dd>
          <dt>Base URL</dt><dd>{{ llmSettings.base_url || '—' }}</dd>
          <dt>API ключ</dt><dd class="mono">{{ llmSettings.api_key }}</dd>
          <dt>Модель</dt><dd>{{ llmSettings.model || '—' }}</dd>
          <dt>Temperature</dt><dd>{{ llmSettings.temperature ?? '—' }}</dd>
          <dt>Max output tokens</dt><dd>{{ llmSettings.max_output_tokens ?? 'не задан' }}</dd>
        </dl>
      </div>

      <div v-if="loadingLlm" class="dim">Загрузка…</div>
    </section>
  </div>
</template>

<style scoped>
.admin-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tab-bar {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.tab-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Stat cards */
.stat-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px;
  text-align: center;
}

.stat-label {
  font-size: 13px;
  margin-bottom: 4px;
}

.stat-num {
  font-size: 28px;
  font-weight: 700;
  font-family: Consolas, monospace;
  color: var(--accent);
}

.stat-error {
  color: var(--danger-text);
}

/* Section title */
.section-title {
  font-size: 14px;
  font-weight: 600;
  margin: 8px 0 4px;
  color: var(--text-dim);
}

/* Table actions */
.table-actions {
  display: flex;
  justify-content: flex-end;
}

/* Data table */
.table-wrap {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  white-space: nowrap;
}

.data-table th {
  text-align: left;
  padding: 6px 8px;
  color: var(--text-dim);
  font-weight: 600;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  background: var(--bg-panel);
}

.data-table td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}

/* Add user form */
.add-user-summary {
  cursor: pointer;
  font-size: 13px;
  color: var(--text-dim);
  padding: 4px 0;
  user-select: none;
}

.add-user-summary:hover {
  color: var(--text);
}

.add-user-form {
  margin-top: 8px;
}

.field-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.field-row input,
.field-row select {
  padding: 5px 8px;
  font-size: 13px;
}

/* Actions cell */
.actions-cell {
  display: flex;
  gap: 4px;
  align-items: center;
  flex-wrap: wrap;
}

/* LLM form */
.llm-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 500px;
}

.llm-form input,
.llm-form select {
  width: 100%;
}

.form-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.llm-saved {
  padding: 12px;
}

.llm-saved h4 {
  font-size: 13px;
  margin: 0 0 8px;
  color: var(--text-dim);
}

.kv-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 6px 16px;
  font-size: 13px;
  margin: 0;
}

.kv-grid dt {
  color: var(--text-dim);
}

.kv-grid dd {
  margin: 0;
  font-family: Consolas, monospace;
}
</style>
