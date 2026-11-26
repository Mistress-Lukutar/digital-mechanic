<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import type { TicketDraftEvent, ChatMessage, DiagnosticResult } from '../types'
import { createSseChat } from '../composables/useSseChat'
import { resetChat } from '../api'
import StatusCard from '../components/StatusCard.vue'
import AgentStep from '../components/AgentStep.vue'
import TicketForm from '../components/TicketForm.vue'
import HistoryPanel from '../components/HistoryPanel.vue'
import DocPanel from '../components/DocPanel.vue'
import AppModal from '../components/AppModal.vue'
import { renderAssistantHtml } from '../lib/markdown'

const props = defineProps<{ vehicleId: string }>()
const emit = defineEmits<{ back: [] }>()

interface VehicleHeader {
  garageNo: string; make: string; model: string | null; engineModel: string
  sessionStatus: string | null; sessionAnomalyTitle: string | null; sessionAnomalyType: string | null
}

const header = ref<VehicleHeader>({
  garageNo: '', make: '', model: null, engineModel: '',
  sessionStatus: null, sessionAnomalyTitle: null, sessionAnomalyType: null,
})

async function fetchVehicleInfo(): Promise<void> {
  try {
    const detail = await import('../api').then(m => m.getVehicleDetail(props.vehicleId))
    header.value.garageNo = detail.garage_no || ''
    header.value.make = detail.make || ''
    header.value.model = detail.model ?? null
    header.value.engineModel = detail.engine_model || ''
    const sessions = detail.sessions ?? []
    if (sessions.length > 0) {
      const latest = sessions[0]
      header.value.sessionStatus = latest.status
      header.value.sessionAnomalyTitle = latest.anomaly_title
      header.value.sessionAnomalyType = latest.anomaly_type
    }
  } catch { /* keep defaults */ }
}
fetchVehicleInfo()

const chat = createSseChat({
  onTicketDraft(draft: TicketDraftEvent): void { ticketDraft.value = draft; showTicketModal.value = true },
  onDocument(docId: string, page: number): void { activeDocId.value = docId; activePage.value = page; rightPanelTab.value = 'doc' },
})

const messages = chat.messages
const streaming = chat.streaming
const chatError = chat.error
const messageInput = ref('')

async function sendMessage(): Promise<void> {
  const text = messageInput.value.trim()
  if (!text || streaming.value) return
  messageInput.value = ''
  await chat.send(props.vehicleId, text)
  await nextTick()
  scrollToBottom()
}

function scrollToBottom(): void {
  const el = document.querySelector('.chat-messages')
  if (el) el.scrollTop = el.scrollHeight
}

watch(() => messages.value.length, () => { scrollToBottom() }, { flush: 'post' })
watch(() => streaming.value, () => { if (!streaming.value) nextTick(scrollToBottom) })

const quickActions = [
  { label: 'Получить диагностику', text: 'Получить результат диагностики' },
  { label: 'Можно ли перегнать?', text: 'Можно ли перегнать машину своим ходом на базу?' },
  { label: 'Создать заявку', text: 'Создай заявку на дефектовку' },
]

type PanelTab = 'history' | 'doc'
const rightPanelTab = ref<PanelTab>('history')
const showHistoryPanel = ref(false)

function toggleHistory(): void {
  if (rightPanelTab.value === 'history') showHistoryPanel.value = !showHistoryPanel.value
  else { rightPanelTab.value = 'history'; showHistoryPanel.value = true }
}

const activeDocId = ref<string | null>(null)
const activePage = ref<number | null>(null)
const showTicketModal = ref(false)
const ticketDraft = ref<TicketDraftEvent | null>(null)
const historyRefreshKey = ref(0)

function handleTicketSubmitted(_ticketId: string): void {
  showTicketModal.value = false
  ticketDraft.value = null
  historyRefreshKey.value++
}
function handleTicketClose(): void { showTicketModal.value = false; ticketDraft.value = null }

async function handleNewDialog(): Promise<void> {
  try { await resetChat(props.vehicleId) } catch { /* ignore */ }
  chat.resetLocal()
}

function handleMdClick(e: MouseEvent): void {
  const el = (e.target as HTMLElement).closest('a[data-doc-id]')
  if (!el) return
  e.preventDefault()
  activeDocId.value = el.getAttribute('data-doc-id')
  activePage.value = Number(el.getAttribute('data-page'))
  rightPanelTab.value = 'doc'
}

function getDiagFromMsg(msg: ChatMessage): DiagnosticResult | null {
  const extended = msg as ChatMessage & { _diag?: DiagnosticResult }
  return extended._diag ?? null
}

function sessionBadgeClass(status: string | null): string {
  switch (status) { case 'normal': return 'badge-ok'; case 'anomaly': return 'badge-warning'; case 'check_failed': return 'badge-danger'; default: return '' }
}

function sessionLabel(status: string | null): string {
  switch (status) { case 'normal': return 'Норма'; case 'anomaly': return 'Отклонение'; case 'check_failed': return 'Сбой записи'; default: return '\u2014' }
}

function onKeydown(e: KeyboardEvent): void { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() } }
</script>

<template>
  <div class="chat-page">
    <header class="chat-header panel">
      <button class="back-btn" @click="emit('back')">← Назад</button>
      <div class="header-info">
        <div class="header-main">
          <span class="garage-badge">{{ header.garageNo }}</span>
          <span class="vehicle-name">{{ header.make }} {{ header.model || '' }}</span>
        </div>
        <div class="header-meta">
          <span v-if="header.sessionStatus" :class="['badge', sessionBadgeClass(header.sessionStatus)]">{{ sessionLabel(header.sessionStatus) }}</span>
          <span v-if="header.engineModel" class="engine-chip">{{ header.engineModel }}</span>
        </div>
      </div>
      <div class="header-actions">
        <button :disabled="streaming" @click="handleNewDialog">Новый диалог</button>
        <button @click="toggleHistory">История</button>
      </div>
    </header>

    <div class="chat-layout">
      <div class="chat-column">
        <div v-if="chatError" class="error-strip chat-error">
          {{ chatError }}
          <button class="close-error" @click="chatError = null">&times;</button>
        </div>

        <div class="chat-messages">
          <div v-for="(msg, idx) in messages" :key="idx" :class="['message-row', msg.role]">
            <template v-if="msg.role === 'assistant'">
              <div class="bubble assistant-bubble">
                <StatusCard v-if="getDiagFromMsg(msg)" :diag="getDiagFromMsg(msg)" />
                <AgentStep v-for="(step, sIdx) in msg.steps" :key="sIdx" :step="step" />
                <div v-if="msg.text" class="message-text md-body" v-html="renderAssistantHtml(msg.text)" @click="handleMdClick"></div>
              </div>
            </template>
            <template v-else>
              <div class="bubble user-bubble">{{ msg.text }}</div>
            </template>
          </div>

          <div v-if="streaming" class="streaming-indicator">
            <span class="spinner" /><span class="dim">ИИ печатает...</span>
          </div>
        </div>

        <div v-if="!streaming && messages.length === 0" class="quick-actions">
          <button v-for="action in quickActions" :key="action.label" class="quick-chip" @click="messageInput = action.text">{{ action.label }}</button>
        </div>

        <div class="input-row">
          <textarea v-model="messageInput" rows="1" placeholder="Введите сообщение..." :disabled="streaming" @keydown="onKeydown" />
          <button v-if="!streaming" class="send-btn primary" :disabled="!messageInput.trim()" @click="sendMessage">&rarr;</button>
          <button v-else class="stop-btn danger-solid" @click="chat.stop">Стоп</button>
        </div>
      </div>

      <div class="right-panel">
        <div class="panel-tabs">
          <button :class="['tab-btn', { active: rightPanelTab === 'history' }]" @click="rightPanelTab = 'history'">История</button>
          <button :class="['tab-btn', { active: rightPanelTab === 'doc' }]" @click="rightPanelTab = 'doc'">Документ</button>
        </div>
        <template v-if="rightPanelTab === 'history'">
          <HistoryPanel :vehicle-id="props.vehicleId" :refresh-key="historyRefreshKey" />
        </template>
        <template v-else>
          <DocPanel v-if="activeDocId" :doc-id="activeDocId" :page="activePage" />
          <div v-else class="panel-empty dim">Выберите документ из чата</div>
        </template>
      </div>

      <div v-if="showHistoryPanel && rightPanelTab === 'history'" class="mobile-overlay" @click.self="showHistoryPanel = false">
        <div class="mobile-panel-header">
          <h3>История</h3>
          <button class="close-btn" @click="showHistoryPanel = false">&times;</button>
        </div>
        <HistoryPanel :vehicle-id="props.vehicleId" :refresh-key="historyRefreshKey" />
      </div>
    </div>

    <AppModal v-if="showTicketModal && ticketDraft" wide title="Заявка на дефектовку" @close="handleTicketClose">
      <TicketForm :draft="ticketDraft" :vehicle-id="props.vehicleId" @submitted="handleTicketSubmitted" @close="handleTicketClose" />
    </AppModal>
  </div>
</template>

<style scoped>
.chat-page { display: flex; flex-direction: column; height: calc(100vh - 60px); overflow: hidden; }
.chat-header { display: flex; align-items: center; gap: 12px; padding: 8px 12px; margin-bottom: 0; border-radius: var(--radius-lg) var(--radius-lg) 0 0; flex-shrink: 0; }
.back-btn { background: transparent; border: 0; color: var(--text-dim); font-size: 13px; padding: 4px 8px; cursor: pointer; flex-shrink: 0; }
.back-btn:hover { color: var(--accent); }
.header-info { flex: 1; min-width: 0; }
.header-main { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.garage-badge { background: var(--accent-dim); color: var(--text-on-accent); padding: 2px 8px; border-radius: var(--radius-sm); font-size: 12px; font-weight: 700; flex-shrink: 0; }
.vehicle-name { overflow: hidden; text-overflow: ellipsis; }
.header-meta { display: flex; align-items: center; gap: 6px; margin-top: 2px; }
.engine-chip { background: var(--bg-input); border: 1px solid var(--border); color: var(--text-dim); padding: 1px 8px; border-radius: 999px; font-size: 11px; }
.header-actions { display: flex; gap: 6px; flex-shrink: 0; }
.chat-layout { display: flex; flex: 1; min-height: 0; overflow: hidden; }
.chat-column { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.chat-messages { flex: 1; overflow-y: auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 8px; }
.message-row { display: flex; flex-shrink: 0; }
.message-row.user { justify-content: flex-end; }
.message-row.assistant { justify-content: flex-start; }
.bubble { max-width: 85%; padding: 10px 14px; border-radius: var(--radius-lg); font-size: 13px; line-height: 1.5; }
.assistant-bubble { background: var(--bg-panel); border: 1px solid var(--border); border-top-left-radius: 4px; }
.user-bubble { background: var(--accent-dim); color: var(--text-on-accent); border-top-right-radius: 4px; white-space: pre-wrap; }
.message-text { margin: 8px 0 0; word-break: break-word; font-size: 13px; line-height: 1.5; }
.md-body :deep(.citation-link) { color: var(--accent); text-decoration: underline dotted; cursor: pointer; font-size: 12px; padding: 0 2px; }
.md-body :deep(.citation-link:hover) { color: var(--accent); text-decoration: underline; }
.md-body :deep(p) { margin: 0 0 8px; }
.md-body :deep(p:last-child) { margin-bottom: 0; }
.md-body :deep(ul), .md-body :deep(ol) { margin: 4px 0 8px; padding-left: 20px; }
.md-body :deep(li) { margin: 2px 0; }
.md-body :deep(li > p) { margin: 0; }
.md-body :deep(code) { background: var(--bg-input); border: 1px solid var(--border); border-radius: 4px; padding: 1px 5px; font-size: 12px; font-family: ui-monospace, monospace; }
.md-body :deep(pre) { background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 10px; overflow-x: auto; margin: 6px 0; }
.md-body :deep(pre code) { background: transparent; border: 0; padding: 0; }
.md-body :deep(blockquote) { border-left: 3px solid var(--border); margin: 6px 0; padding: 2px 10px; color: var(--text-dim); }
.md-body :deep(h1) { font-size: 15px; margin: 10px 0 4px; }
.md-body :deep(h2) { font-size: 14px; margin: 10px 0 4px; }
.md-body :deep(h3), .md-body :deep(h4) { font-size: 13px; margin: 10px 0 4px; }
.md-body :deep(h1:first-child), .md-body :deep(h2:first-child), .md-body :deep(h3:first-child), .md-body :deep(h4:first-child) { margin-top: 0; }
.md-body :deep(table) { border-collapse: collapse; margin: 6px 0; font-size: 12px; }
.md-body :deep(th), .md-body :deep(td) { border: 1px solid var(--border); padding: 4px 8px; }
.md-body :deep(a) { color: var(--accent); }
.md-body :deep(hr) { border: 0; border-top: 1px solid var(--border); margin: 8px 0; }
.streaming-indicator { display: flex; align-items: center; gap: 8px; padding: 8px 16px; font-size: 12px; }
.spinner { width: 14px; height: 14px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.quick-actions { display: flex; gap: 6px; padding: 8px 16px; flex-wrap: wrap; }
.quick-chip { background: var(--bg-input); border: 1px solid var(--border); color: var(--text-dim); padding: 4px 12px; font-size: 12px; border-radius: 999px; cursor: pointer; }
.quick-chip:hover { border-color: var(--accent); color: var(--accent); }
.input-row { display: flex; align-items: flex-end; gap: 8px; padding: 12px 16px; background: var(--bg-panel); border-top: 1px solid var(--border); flex-shrink: 0; }
.input-row textarea { flex: 1; resize: none; min-height: 36px; max-height: 120px; padding: 8px 12px; font-size: 14px; font-family: inherit; }
.send-btn { width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; font-size: 18px; padding: 0; flex-shrink: 0; }
.stop-btn { width: 40px; height: 4
0; height: 40px; display: flex; align-items: center; justify-content: center; font-size: 13px; padding: 0; flex-shrink: 0; }
.chat-error { position: relative; margin: 8px 16px 0; }
.close-error { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: none; border: 0; color: var(--danger-text); font-size: 16px; padding: 4px; cursor: pointer; }
.right-panel { width: 380px; flex-shrink: 0; border-left: 1px solid var(--border); background: var(--bg-panel); display: flex; flex-direction: column; overflow: hidden; }
.panel-tabs { display: flex; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.tab-btn { flex: 1; background: transparent; border: 0; border-bottom: 2px solid transparent; color: var(--text-dim); padding: 8px; font-size: 13px; cursor: pointer; min-height: auto; }
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
.panel-empty { padding: 24px; text-align: center; }
.mobile-overlay { position: fixed; inset: 0; background: var(--overlay); z-index: 150; display: flex; flex-direction: column; }
.mobile-panel-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; background: var(--bg-panel); border-bottom: 1px solid var(--border); }
.close-btn { background: none; border: 0; color: var(--text-dim); font-size: 24px; padding: 0 4px; cursor: pointer; }
@media (max-width: 1023px) { .right-panel { display: none; } }
</style>
