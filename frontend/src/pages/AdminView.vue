<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { UsageTotals, UsageRowItem, ChatTurnDetail, AdminUserItem, LlmSettingsView } from '../types'
import { getAdminUsageTotals, getAdminUsageRecent, getAdminUsers, createAdminUser, deleteAdminUser, resetAdminPassword, getLlmSettings, updateLlmSettings, getAdminUsageDetail } from '../api'
import { useConfirm } from '../composables/useConfirm'
import { t } from '../i18n'

const { confirm } = useConfirm()

type TabKey = 'dashboard' | 'users' | 'llm'
const activeTab = ref<TabKey>('dashboard')

// Dashboard data
const usageTotals = ref<UsageTotals | null>(null)
const recentUsage = ref<UsageRowItem[]>([])
const loadingData = ref(false)
const errorStrip = ref<string | null>(null)

// Detail row expand/collapse
const expandedUsageId = ref<number | null>(null)
const usageDetail = ref<ChatTurnDetail | null>(null)
const detailLoading = ref(false)
const detailError = ref('')

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
    title: t('admin.delete_user_title'),
    message: t('admin.delete_user_message', { username }),
    confirmLabel: t('admin.delete'),
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
    userError.value = t('admin.password_min_8')
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

async function toggleDetailRow(id: number): Promise<void> {
  if (expandedUsageId.value === id) {
    expandedUsageId.value = null
    usageDetail.value = null
    detailLoading.value = false
    detailError.value = ''
    return
  }
  expandedUsageId.value = id
  usageDetail.value = null
  detailLoading.value = true
  detailError.value = ''
  try {
    const detail = await getAdminUsageDetail(id)
    // Stale-response guard: the user may expand another row while this
    // fetch is in flight; apply only if the target row is still expanded.
    if (expandedUsageId.value === id) usageDetail.value = detail
  } catch (e) {
    if (e instanceof Error && expandedUsageId.value === id) detailError.value = e.message
  } finally {
    if (expandedUsageId.value === id) detailLoading.value = false
  }
}
</script>

<template>
  <div class="admin-view">
    <!-- Tab buttons -->
    <div class="tab-bar">
      <button
        :class="['chip', { active: activeTab === 'dashboard' }]"
        @click="activeTab = 'dashboard'"
      >{{ t('admin.tab.dashboard') }}</button>
      <button
        :class="['chip', { active: activeTab === 'users' }]"
        @click="activeTab = 'users'"
      >{{ t('admin.tab.users') }}</button>
      <button
        :class="['chip', { active: activeTab === 'llm' }]"
        @click="activeTab = 'llm'"
      >{{ t('admin.tab.llm') }}</button>
    </div>

    <!-- Dashboard tab -->
    <section v-if="activeTab === 'dashboard'" class="tab-content">
      <h3>{{ t('admin.dashboard.title') }}</h3>

      <!-- 4 stat cards -->
      <div class="stat-cards">
        <div class="stat-card panel">
          <span class="stat-label dim">{{ t('admin.stat.requests') }}</span>
          <span class="stat-num">{{ usageTotals?.requests_total ?? '—' }}</span>
        </div>
        <div class="stat-card panel">
          <span class="stat-label dim">{{ t('admin.stat.errors') }}</span>
          <span class="stat-num stat-error">{{ usageTotals?.requests_error ?? '—' }}</span>
        </div>
        <div class="stat-card panel">
          <span class="stat-label dim">{{ t('admin.stat.input_tokens') }}</span>
          <span class="stat-num">{{ usageTotals?.input_tokens ?? '—' }}</span>
        </div>
        <div class="stat-card panel">
          <span class="stat-label dim">{{ t('admin.stat.output_tokens') }}</span>
          <span class="stat-num">{{ usageTotals?.output_tokens ?? '—' }}</span>
        </div>
      </div>

      <!-- Recent requests table -->
      <h4 class="section-title">{{ t('admin.recent_requests') }}</h4>
      <div v-if="recentUsage.some(r => r.kind === 'chat' && r.status === 'ok')" class="dim" style="font-size: 12px;">
        {{ t('admin.detail_hint') }}
      </div>
      <div class="table-actions">
        <button :disabled="loadingData" @click="loadDashboard()">{{ t('admin.refresh') }}</button>
      </div>

      <div v-if="errorStrip" class="error-strip">{{ errorStrip }}</div>

      <div v-if="loadingData" class="dim">{{ t('admin.loading') }}</div>

      <div v-else class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>{{ t('admin.table.time') }}</th>
              <th>{{ t('admin.table.user') }}</th>
              <th>{{ t('admin.table.kind') }}</th>
              <th>{{ t('admin.table.model') }}</th>
              <th>{{ t('admin.table.vehicle_id') }}</th>
              <th>{{ t('admin.table.input_tokens') }}</th>
              <th>{{ t('admin.table.output_tokens') }}</th>
              <th>{{ t('admin.table.duration') }}</th>
              <th>{{ t('admin.table.status') }}</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="r in recentUsage" :key="r.id">
              <tr :class="['usage-row', { clickable: r.kind === 'chat' && r.status === 'ok' }]"
                  @click="r.kind === 'chat' && r.status === 'ok' ? toggleDetailRow(r.id) : undefined">
                <td class="mono">
                  <span v-if="r.kind === 'chat' && r.status === 'ok'" class="expand-indicator">{{ expandedUsageId === r.id ? '▾' : '▸' }}</span>
                  {{ formatIso(r.ts) }}
                </td>
                <td>{{ r.username || '—' }}</td>
                <td><span :class="['chip', kindChipClass(r.kind)]">{{ r.kind }}</span></td>
                <td class="dim mono">{{ r.model || '—' }}</td>
                <td class="mono dim">{{ r.vehicle_id || '—' }}</td>
                <td class="mono">{{ r.input_tokens }}</td>
                <td class="mono">{{ r.output_tokens }}</td>
                <td class="mono">{{ r.duration_ms }}</td>
                <td>
                  <span v-if="r.status === 'ok'" class="badge badge-ok">OK</span>
                  <span v-else class="badge badge-danger" :title="r.error || ''">{{ t('admin.error_label') }}</span>
                </td>
              </tr>
              <tr v-if="expandedUsageId === r.id" class="detail-row">
                <td :colspan="9">
                  <div v-if="detailLoading" class="dim">{{ t('admin.detail_loading') }}</div>
                  <div v-else-if="detailError" class="badge badge-danger">{{ detailError }}</div>
                  <template v-else-if="usageDetail">
                    <div style="margin-bottom: 8px;">
                      <span class="detail-label">{{ t('admin.detail_question') }}:</span>
                      <pre class="mono pre-wrap">{{ usageDetail.question }}</pre>
                    </div>
                    <div style="margin-bottom: 8px;">
                      <span class="detail-label">{{ t('admin.detail_answer') }}:</span>
                      <pre class="mono pre-wrap dim">{{ usageDetail.answer }}</pre>
                    </div>
                    <div v-if="usageDetail.tools.length" style="margin-bottom: 8px;">
                      <span class="detail-label">{{ t('admin.detail_tools') }}:</span>
                      <span v-for="tool in usageDetail.tools" :key="tool" class="chip" style="margin-left: 4px;">{{ tool }}</span>
                    </div>
                    <div v-if="usageDetail.citations.length" style="margin-bottom: 8px;">
                      <span class="detail-label">{{ t('admin.detail_citations') }}:</span>
                      <span v-for="(c, ci) in usageDetail.citations" :key="ci" class="chip" style="margin-left: 4px;">[{{ c.doc }}, стр. {{ c.page }}]</span>
                    </div>
                    <div v-if="usageDetail.ticket_draft" style="margin-bottom: 8px;">
                      <span class="detail-label">{{ t('admin.detail_ticket_draft') }}:</span>
                      <span v-if="usageDetail.ticket_draft.anomaly_type" class="chip" style="margin-left: 4px;">{{ usageDetail.ticket_draft.anomaly_type }}</span>
                      <span v-if="usageDetail.ticket_draft.urgency" class="chip" style="margin-left: 4px;">{{ usageDetail.ticket_draft.urgency }}</span>
                    </div>
                    <div v-if="usageDetail.has_image" style="margin-bottom: 8px;">
                      <span class="chip">📷 {{ t('admin.detail_image') }}</span>
                    </div>
                    <div v-if="usageDetail.language">
                      <span class="chip dim">lang: {{ usageDetail.language }}</span>
                    </div>
                  </template>
                </td>
              </tr>
            </template>
          </tbody>
        </table>

        <div v-if="recentUsage.length === 0" class="dim" style="padding: 16px; text-align: center;">
          {{ t('admin.no_records') }}
        </div>
      </div>
    </section>

    <!-- Users tab -->
    <section v-if="activeTab === 'users'" class="tab-content">
      <h3>{{ t('admin.users.title') }}</h3>

      <!-- Add user form -->
      <details :open="addUserOpen" @toggle="addUserOpen = ($event.target as HTMLDetailsElement).open">
        <summary class="add-user-summary">{{ t('admin.add_user') }}</summary>
        <form class="add-user-form" @submit.prevent="handleCreateUser">
          <div class="field-row">
            <input v-model="newUser.username" :placeholder="t('admin.username_placeholder')" required />
            <input v-model="newUser.password" type="password" :placeholder="t('admin.password_placeholder')" required minlength="8" autocomplete="new-password" />
            <select v-model="newUser.role">
              <option value="user">пользователь</option>
              <option value="admin">админ</option>
            </select>
            <button type="submit" class="primary">{{ t('admin.create') }}</button>
          </div>
        </form>
      </details>

      <!-- Error strip -->
      <div v-if="userError" class="error-strip">{{ userError }}</div>

      <!-- Users table -->
      <div v-if="loadingUsers" class="dim">{{ t('admin.loading') }}</div>
      <template v-else>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>{{ t('admin.table.name') }}</th>
                <th>{{ t('admin.table.role') }}</th>
                <th>{{ t('admin.table.change_password') }}</th>
                <th>{{ t('admin.table.created_at') }}</th>
                <th>{{ t('admin.table.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in users" :key="u.username">
                <td class="mono">{{ u.username }}</td>
                <td><span :class="['chip', u.role === 'admin' ? '' : 'badge-ok']">{{ u.role }}</span></td>
                <td>
                  <span v-if="u.must_change_password" class="badge badge-warning">{{ t('admin.must_change_pw') }}</span>
                  <span v-else class="dim">—</span>
                </td>
                <td class="mono dim">{{ formatIso(u.created_at) }}</td>
                <td class="actions-cell">
                  <!-- Reset password: inline form -->
                  <template v-if="resettingPassword[u.username]">
                    <input
                      v-model="newPasswords[u.username]"
                      type="password"
                      :placeholder="t('admin.new_password_placeholder')"
                      autocomplete="new-password"
                      style="width: 120px; padding: 3px 6px;"
                      @keydown.enter="handleResetPassword(u.username)"
                    />
                    <button :disabled="!newPasswords[u.username]" class="primary" style="padding: 2px 8px; font-size: 12px; min-height: auto;" @click="handleResetPassword(u.username)">
                      {{ resettingPassword[u.username] ? t('admin.loading_indicator') : 'OK' }}
                    </button>
                  </template>
                  <template v-else>
                    <button style="padding: 2px 8px; font-size: 12px; min-height: auto;" @click="newPasswords[u.username] = ''; resettingPassword[u.username] = true">{{ t('admin.reset_password') }}</button>
                  </template>
                  <button class="danger-solid" style="padding: 2px 8px; font-size: 12px; min-height: auto;" @click="handleDeleteUser(u.username)">{{ t('admin.delete') }}</button>
                </td>
              </tr>
            </tbody>
          </table>

          <div v-if="users.length === 0" class="dim" style="padding: 16px; text-align: center;">
            {{ t('admin.no_users') }}
          </div>
        </div>
      </template>
    </section>

    <!-- LLM settings tab -->
    <section v-if="activeTab === 'llm'" class="tab-content">
      <h3>{{ t('admin.settings.title') }}</h3>

      <div v-if="llmError" class="error-strip">{{ llmError }}</div>

      <form v-if="!loadingLlm && llmSettings" class="llm-form" @submit.prevent="handleSaveLlm">
        <div class="field">
          <label class="label">{{ t('admin.protocol_label') }}</label>
          <select v-model="llmForm.protocol">
            <option value="openai_compatible">openai_compatible</option>
            <option value="anthropic">anthropic</option>
            <option value="google_gemini">google_gemini</option>
          </select>
        </div>

        <div class="field">
          <label class="label">{{ t('admin.base_url_label') }}</label>
          <input v-model="llmForm.base_url" type="url" placeholder="https://api.example.com/v1" />
        </div>

        <div class="field">
          <label class="label">{{ t('admin.api_key_label') }}</label>
          <input
            v-model="llmForm.api_key"
            type="password"
            autocomplete="off"
            :placeholder="llmSettings.api_key || t('admin.not_set')"
          />
          <span class="field-hint dim">{{ t('admin.api_key_hint') }}</span>
        </div>

        <div class="field">
          <label class="label">{{ t('admin.model_label') }}</label>
          <input v-model="llmForm.model" type="text" placeholder="model-name" />
        </div>

        <div class="field">
          <label class="label">{{ t('admin.temperature_label') }}</label>
          <input v-model.number="llmForm.temperature" type="number" min="0" max="1" step="0.1" />
        </div>

        <div class="field">
          <label class="label">{{ t('admin.max_output_tokens_label') }}</label>
          <input v-model.number="llmForm.max_output_tokens" type="number" :placeholder="t('admin.empty_no_limit')" />
        </div>

        <div class="form-actions">
          <button type="submit" :disabled="savingLlm" class="primary">{{ t('admin.save') }}</button>
          <span v-if="savingLlm" class="dim">{{ t('admin.saving') }}</span>
        </div>
      </form>

      <!-- Saved state display -->
      <div v-if="llmSettings && !savingLlm" class="llm-saved panel">
        <h4>{{ t('admin.current_settings') }}</h4>
        <dl class="kv-grid">
          <dt>{{ t('admin.protocol_label') }}</dt><dd>{{ llmSettings.protocol }}</dd>
          <dt>{{ t('admin.base_url_label') }}</dt><dd>{{ llmSettings.base_url || '—' }}</dd>
          <dt>{{ t('admin.api_key_label') }}</dt><dd class="mono">{{ llmSettings.api_key }}</dd>
          <dt>{{ t('admin.model_label') }}</dt><dd>{{ llmSettings.model || '—' }}</dd>
          <dt>{{ t('admin.temperature_label') }}</dt><dd>{{ llmSettings.temperature ?? '—' }}</dd>
          <dt>{{ t('admin.max_output_tokens_label') }}</dt><dd>{{ llmSettings.max_output_tokens ?? t('admin.not_set') }}</dd>
        </dl>
      </div>

      <div v-if="loadingLlm" class="dim">{{ t('admin.loading') }}</div>
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

/* Expandable usage rows */
.data-table tbody tr.clickable {
  cursor: pointer;
}

.expand-indicator {
  display: inline-block;
  width: 14px;
  text-align: center;
  margin-right: 2px;
  font-size: 10px;
  color: var(--text-dim);
  user-select: none;
}

/* Detail row */
.detail-row td {
  background: rgba(255, 255, 255, 0.03);
  padding: 12px 8px;
  border-bottom: 1px solid var(--border);
}

.detail-label {
  font-size: 12px;
  color: var(--text-dim);
  margin-right: 4px;
}

.pre-wrap {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
}
</style>
