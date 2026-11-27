<script setup lang="ts">
import { ref, nextTick, watch, computed } from 'vue'
import type { TicketDraftEvent, ChatMessage, DiagnosticResult } from '../types'
import { t } from '../i18n'
import { createSseChat } from '../composables/useSseChat'
import { useSpeech } from '../composables/useSpeech'
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
  if (!props.vehicleId) return
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
  onDocument(docId: string, page: number): void {
    activeDocId.value = docId; activePage.value = page
    if (!isMobileLayout()) rightOpen.value = true
  },
})

const speech = useSpeech()
// Top-level aliases: nested refs inside a plain object are NOT auto-unwrapped
// in templates, so the mic bindings must live at setup scope.
const micSupported = speech.supported
const micListening = speech.listening

const messages = chat.messages
const streaming = chat.streaming
const chatError = chat.error
const expandedReasoning = ref<Record<number, boolean>>({})
const messageInput = ref('')
const inputEl = ref<HTMLTextAreaElement | null>(null)
const attachedImage = ref<string | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

function autoGrow(e: Event): void {
  const t = e.target as HTMLTextAreaElement; t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 120) + 'px'
}

function onFileSelected(e: Event): void {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (): void => {
    const dataUrl = reader.result as string
    // Downscale with canvas to max 1024px side, JPEG 0.85 quality
    const img = new Image()
    img.onload = (): void => {
      const canvas = document.createElement('canvas')
      let w = img.width
      let h = img.height
      if (w > 1024 || h > 1024) {
        if (w > h) { h = (h * 1024) / w; w = 1024 }
        else { w = (w * 1024) / h; h = 1024 }
      }
      canvas.width = w
      canvas.height = h
      const ctx = canvas.getContext('2d')!
      ctx.drawImage(img, 0, 0, w, h)
      attachedImage.value = canvas.toDataURL('image/jpeg', 0.85)
    }
    img.src = dataUrl
  }
  reader.readAsDataURL(file)
  // Reset input so same file can be re-selected
  ;(e.target as HTMLInputElement).value = ''
}

async function sendMessage(): Promise<void> {
  const text = messageInput.value.trim()
  if (!text || streaming.value) return
  if (!props.vehicleId) return
  messageInput.value = ''
  const img = attachedImage.value
  attachedImage.value = null
  await chat.send(props.vehicleId, text, null, img ?? undefined)
  await nextTick()
  if (inputEl.value) inputEl.value.style.height = 'auto'
  scrollToBottom()
}

function scrollToBottom(): void {
  const el = document.querySelector('.chat-messages')
  if (el) el.scrollTop = el.scrollHeight
}

watch(() => messages.value.length, () => { scrollToBottom() }, { flush: 'post' })
watch(() => streaming.value, () => { if (!streaming.value) nextTick(scrollToBottom) })
watch(
  () => {
    const last = messages.value[messages.value.length - 1]
    if (!last) return 0
    return last.text.length + last.steps.length * 1000
  },
  () => {
    const el = document.querySelector('.chat-messages')
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    if (nearBottom) scrollToBottom()
  },
  { flush: 'post' },
)

const quickActions = computed(() => [
  { label: t('chat.quick.diagnostic.label'), text: t('chat.quick.diagnostic.text') },
  { label: t('chat.quick.can_move.label'), text: t('chat.quick.can_move.text') },
  { label: t('chat.quick.ticket.label'), text: t('chat.quick.ticket.text') },
])

const leftOpen = ref(true)
const rightOpen = ref(false)
const mobilePanel = ref<'history' | 'doc' | null>(null)

function isMobileLayout(): boolean {
  return window.matchMedia('(max-width: 1023px)').matches
}

function toggleSidebar(side: 'left' | 'right'): void {
  if (isMobileLayout()) {
    // On mobile both sidebars render as full-screen overlays keyed by panel name.
    const panel = side === 'left' ? 'history' : 'doc'
    mobilePanel.value = mobilePanel.value === panel ? null : panel
  } else if (side === 'left') {
    leftOpen.value = !leftOpen.value
  } else {
    rightOpen.value = !rightOpen.value
  }
}

const activeDocId = ref<string | null>(null)
const activePage = ref<number | null>(null)
const showTicketModal = ref(false)
const ticketDraft = ref<TicketDraftEvent | null>(null)
const historyRefreshKey = ref(0)

function handleTicketSubmitted(_ticketId: string): void {
  historyRefreshKey.value++
}
function handleTicketClose(): void { showTicketModal.value = false; ticketDraft.value = null }

async function handleNewDialog(): Promise<void> {
  if (!props.vehicleId) return
  try { await resetChat(props.vehicleId) } catch { /* ignore */ }
  chat.resetLocal()
}

function handleMdClick(e: MouseEvent): void {
  const el = (e.target as HTMLElement).closest('a[data-doc-id]')
  if (!el) return
  e.preventDefault()
  activeDocId.value = el.getAttribute('data-doc-id')
  activePage.value = Number(el.getAttribute('data-page'))
  if (isMobileLayout()) mobilePanel.value = 'doc'
  else rightOpen.value = true
}

function getDiagFromMsg(msg: ChatMessage): DiagnosticResult | null {
  const extended = msg as ChatMessage & { _diag?: DiagnosticResult }
  return extended._diag ?? null
}

function sessionBadgeClass(status: string | null): string {
  switch (status) { case 'normal': return 'badge-ok'; case 'anomaly': return 'badge-warning'; case 'check_failed': return 'badge-danger'; default: return '' }
}

function sessionLabel(status: string | null): string {
  switch (status) { case 'normal': return t('status.label.normal'); case 'anomaly': return t('status.label.anomaly'); case 'check_failed': return t('status.label.check_failed'); default: return '\u2014' }
}

function onKeydown(e: KeyboardEvent): void { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() } }

function handleVoiceText(text: string): void {
  const sep = messageInput.value.trim() ? ' ' : ''
  messageInput.value += sep + text
  autoGrow({ target: inputEl.value as unknown as EventTarget } as Event)
  if (inputEl.value) inputEl.value.focus()
}

function toggleMic(): void {
  if (speech.listening.value) {
    speech.stop()
  } else {
    speech.start(handleVoiceText)
  }
}
</script>

<template>
  <div class="chat-page">
    <aside v-show="leftOpen" class="chat-sidebar left">
      <button class="new-dialog-btn" :disabled="streaming" @click="handleNewDialog">{{ t('chat.new_dialog') }}</button>
      <HistoryPanel :vehicle-id="props.vehicleId" :refresh-key="historyRefreshKey" />
    </aside>

    <div class="chat-column">
      <header class="chat-header panel">
        <button
          class="sidebar-toggle"
          :class="{ active: isMobileLayout() ? mobilePanel === 'history' : leftOpen }"
          :title="t('chat.history')"
          :aria-label="t('chat.history')"
          @click="toggleSidebar('left')"
        >
          <svg class="toggle-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M3 6h18M3 12h18M3 18h18"/>
          </svg>
        </button>
        <button class="back-btn" @click="emit('back')">← {{ t('chat.back') }}</button>
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
        <button
          class="sidebar-toggle"
          :class="{ active: isMobileLayout() ? mobilePanel === 'doc' : rightOpen }"
          :title="t('chat.document')"
          :aria-label="t('chat.document')"
          @click="toggleSidebar('right')"
        >
          <svg class="toggle-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <path d="M14 2v6h6"/>
          </svg>
        </button>
      </header>

      <div v-if="chatError" class="error-strip chat-error">
        {{ chatError }}
        <button class="close-error" @click="chatError = null">&times;</button>
      </div>

      <div class="chat-messages">
        <div v-for="(msg, idx) in messages" :key="idx" :class="['message-row', msg.role]">
          <template v-if="msg.role === 'assistant'">
            <div class="bubble assistant-bubble">
              <template v-if="msg.reasoning && msg.reasoning.length > 0">
                <button
                  class="reasoning-toggle"
                  @click="expandedReasoning[idx] = !expandedReasoning[idx]"
                  :aria-expanded="!!expandedReasoning[idx]"
                >
                  <span :class="{ chevron: true, open: !!expandedReasoning[idx] }">▸</span>
                  {{ t('chat.reasoning.toggle') }}
                </button>
                <div class="reasoning-body" v-show="expandedReasoning[idx]">{{ msg.reasoning }}</div>
              </template>
              <StatusCard v-if="getDiagFromMsg(msg)" :diag="getDiagFromMsg(msg)" />
              <AgentStep v-for="(step, sIdx) in msg.steps" :key="sIdx" :step="step" />
              <div v-if="msg.text" class="message-text md-body" v-html="renderAssistantHtml(msg.text)" @click="handleMdClick"></div>
            </div>
          </template>
          <template v-else>
            <div class="bubble user-bubble">
              <img v-if="msg.image" :src="msg.image" class="user-image-thumb" />
              {{ msg.text }}
            </div>
          </template>
        </div>

        <div v-if="streaming" class="streaming-indicator">
          <span class="spinner" /><span class="dim">{{ t('chat.streaming') }}</span>
        </div>

        <!-- Quick actions: centered in the chat area when empty with vehicle -->
        <div v-if="!streaming && messages.length === 0 && vehicleId" class="quick-actions">
          <button v-for="action in quickActions" :key="action.label" class="quick-chip" @click="messageInput = action.text">{{ action.label }}</button>
        </div>

        <!-- Empty vehicle banner: centered when no vehicle selected -->
        <div v-if="!vehicleId && !streaming" class="chat-empty-banner panel">
          <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          <span>{{ t('chat.empty_vehicle') }}</span>
        </div>
      </div>

      <div v-if="attachedImage && vehicleId" class="image-preview-chip">
        <img :src="attachedImage" alt="" class="preview-thumb" />
        <button class="remove-btn" @click="attachedImage = null" :title="t('chat.attach.remove')">&times;</button>
      </div>
      <div class="input-row" v-if="vehicleId">
        <textarea v-model="messageInput" rows="1" :placeholder="t('chat.input.placeholder')" :disabled="streaming || !vehicleId" @keydown="onKeydown" @input="autoGrow" />
        <input type="file" accept="image/*" ref="fileInput" style="display:none" @change="onFileSelected" />
        <button
          v-if="!streaming && vehicleId"
          class="attach-btn"
          :title="t('chat.attach.label')"
          aria-label="Прикрепить изображение"
          @click="fileInput?.click()"
        >
          <svg class="attach-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
          </svg>
        </button>
        <button
          v-if="micSupported && !streaming && vehicleId"
          class="mic-btn"
          :class="{ listening: micListening }"
          :title="micListening ? t('chat.mic.listening') : t('chat.mic.label')"
          :aria-label="micListening ? t('chat.mic.listening') : t('chat.mic.label')"
          @click="toggleMic"
        >
          <svg class="mic-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <rect x="9" y="2" width="6" height="12" rx="3"/>
            <path d="M5 11a7 7 0 0 0 14 0H5z"/>
          </svg>
        </button>
        <button v-if="!streaming" class="send-btn primary" :disabled="!messageInput.trim() || !vehicleId" @click="sendMessage">&rarr;</button>
        <button v-else class="stop-btn danger-solid" @click="chat.stop">{{ t('chat.stop') }}</button>
      </div>
      </div>

      <aside v-show="rightOpen" class="chat-sidebar right">
        <DocPanel v-if="activeDocId" :doc-id="activeDocId" :page="activePage" />
        <div v-else class="panel-empty dim">{{ t('chat.select_doc') }}</div>
      </aside>

      <div v-if="mobilePanel === 'history'" class="mobile-overlay" @click.self="mobilePanel = null">
        <div class="mobile-panel-header">
          <h3>{{ t('chat.history') }}</h3>
          <button class="close-btn" @click="mobilePanel = null">&times;</button>
        </div>
        <HistoryPanel :vehicle-id="props.vehicleId" :refresh-key="historyRefreshKey" />
      </div>

      <div v-if="mobilePanel === 'doc'" class="mobile-overlay" @click.self="mobilePanel = null">
        <div class="mobile-panel-header">
          <h3>{{ t('chat.document') }}</h3>
          <button class="close-btn" @click="mobilePanel = null">&times;</button>
        </div>
        <DocPanel :doc-id="activeDocId!" :page="activePage" />
      </div>

    <AppModal v-if="showTicketModal && ticketDraft" wide title="Заявка на дефектовку" @close="handleTicketClose">
      <TicketForm :draft="ticketDraft" :vehicle-id="props.vehicleId" @submitted="handleTicketSubmitted" @close="handleTicketClose" />
    </AppModal>
  </div>
</template>

<style scoped>
.chat-page { display: flex; flex-direction: row; flex: 1; min-height: 0; overflow: hidden; }
.chat-header { display: flex; align-items: center; gap: 12px; padding: 8px 12px; margin-bottom: 0; border-radius: 0; flex-shrink: 0; min-width: 0; }
.back-btn { background: transparent; border: 0; color: var(--text-dim); font-size: 13px; padding: 4px 8px; cursor: pointer; flex-shrink: 0; }
.back-btn:hover { color: var(--accent); }
.header-info { flex: 1; min-width: 0; }
.header-main { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.garage-badge { background: var(--accent-dim); color: var(--text-on-accent); padding: 2px 8px; border-radius: var(--radius-sm); font-size: 12px; font-weight: 700; flex-shrink: 0; }
.vehicle-name { overflow: hidden; text-overflow: ellipsis; }
.header-meta { display: flex; align-items: center; gap: 6px; margin-top: 2px; }
.engine-chip { background: var(--bg-input); border: 1px solid var(--border); color: var(--text-dim); padding: 1px 8px; border-radius: 999px; font-size: 11px; }
.chat-column { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.chat-sidebar { width: 380px; flex-shrink: 0; display: flex; flex-direction: column; overflow-y: auto; overflow-x: hidden; background: var(--bg-panel); }
.chat-sidebar.left { border-right: 1px solid var(--border); }
.chat-sidebar.right { border-left: 1px solid var(--border); }
.chat-sidebar > * { flex-shrink: 0; }
.new-dialog-btn { margin: 12px; width: calc(100% - 24px); font-size: 13px; }
.sidebar-toggle { width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; background: transparent; border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text-dim); padding: 0; cursor: pointer; flex-shrink: 0; }
.sidebar-toggle:hover { border-color: var(--accent); color: var(--accent); }
.sidebar-toggle.active { border-color: var(--accent); color: var(--accent); }
.toggle-icon { width: 18px; height: 18px; }
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
.quick-actions { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; flex: 1; min-height: 0; padding: 8px 16px; }
.chat-empty-banner { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; flex: 1; min-height: 0; padding: 24px; text-align: center; color: var(--text-dim); font-size: 15px; }
.chat-empty-banner .empty-icon { width: 48px; height: 48px; opacity: 0.4; }
.quick-chip { background: var(--bg-input); border: 1px solid var(--border); color: var(--text-dim); padding: 4px 12px; font-size: 12px; border-radius: 999px; cursor: pointer; }
.quick-chip:hover { border-color: var(--accent); color: var(--accent); }
.input-row { display: flex; align-items: flex-end; gap: 8px; padding: 12px 16px; background: var(--bg-panel); border-top: 1px solid var(--border); flex-shrink: 0; }
.input-row textarea { flex: 1; resize: none; min-height: 36px; max-height: 120px; padding: 8px 12px; font-size: 14px; font-family: inherit; }
.send-btn { width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; font-size: 18px; padding: 0; flex-shrink: 0; }
.stop-btn { width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; font-size: 13px; padding: 0; flex-shrink: 0; }
.attach-btn { width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background: transparent; border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text-dim); padding: 0; cursor: pointer; flex-shrink: 0; }
.attach-btn:hover { border-color: var(--accent); color: var(--accent); }
.attach-icon { width: 20px; height: 20px; }
.mic-btn { width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; background: transparent; border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text-dim); padding: 0; cursor: pointer; flex-shrink: 0; }
.mic-btn:hover { border-color: var(--accent); color: var(--accent); }
.mic-icon { width: 20px; height: 20px; }
@keyframes mic-pulse { 0%, 100% { opacity: 1; box-shadow: none; } 50% { opacity: 0.6; box-shadow: 0 0 8px var(--accent); } }
.image-preview-chip { display: flex; align-items: center; gap: 8px; padding: 8px 16px; background: var(--bg-panel); border-top: 1px solid var(--border); flex-shrink: 0; }
.preview-thumb { width: 48px; height: 48px; object-fit: cover; border-radius: var(--radius-sm); border: 1px solid var(--border); }
.remove-btn { background: transparent; border: none; color: var(--danger-text); font-size: 20px; line-height: 1; cursor: pointer; padding: 4px 8px; flex-shrink: 0; }
.user-image-thumb { max-width: 100%; max-height: 160px; border-radius: var(--radius-sm); margin-bottom: 8px; display: block; object-fit: contain; }
.mic-btn.listening .mic-icon { animation: mic-pulse 1s ease-in-out infinite; }
.chat-error { position: relative; margin: 8px 16px 0; }
.close-error { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: none; border: 0; color: var(--danger-text); font-size: 16px; padding: 4px; cursor: pointer; }
.panel-empty { padding: 24px; text-align: center; }
.mobile-overlay { position: fixed; inset: 0; background: var(--overlay); z-index: 150; display: flex; flex-direction: column; }
.mobile-panel-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; background: var(--bg-panel); border-bottom: 1px solid var(--border); }
.close-btn { background: none; border: 0; color: var(--text-dim); font-size: 24px; padding: 0 4px; cursor: pointer; }
@media (max-width: 1023px) { .chat-sidebar { display: none; } }
@media (min-width: 1024px) { .mobile-overlay { display: none; } }
@media (max-width: 640px) {
  .chat-header { flex-wrap: wrap; row-gap: 4px; }
  .header-info { order: -1; flex-basis: 100%; }
}
.reasoning-toggle { background: transparent; border: 0; color: var(--text-dim); font-size: 12px; cursor: pointer; padding: 2px 4px; line-height: 1; display: inline-flex; align-items: center; gap: 4px; }
.reasoning-toggle:hover { color: var(--accent); }
.chevron { display: inline-block; transition: transform 0.15s ease; font-size: 10px; }
.chevron.open { transform: rotate(90deg); }
.reasoning-body { color: var(--text-dim); font-size: 12px; white-space: pre-wrap; max-height: 180px; overflow-y: auto; margin: 4px 0; line-height: 1.4; }
</style>
