<script setup lang="ts">
import { ref, nextTick, watch, computed, onBeforeUnmount, onMounted } from 'vue'
import type { TicketDraftEvent, ChatMessage, DiagnosticResult } from '../types'
import { t } from '../i18n'
import { createSseChat } from '../composables/useSseChat'
import { useSpeech } from '../composables/useSpeech'
import { getChat, listChats, switchChatBranch } from '../api'
import StatusCard from '../components/StatusCard.vue'
import AgentStep from '../components/AgentStep.vue'
import TicketForm from '../components/TicketForm.vue'
import HistoryPanel from '../components/HistoryPanel.vue'
import ChatsPanel from '../components/ChatsPanel.vue'
import DocPanel from '../components/DocPanel.vue'
import AppModal from '../components/AppModal.vue'
import { renderAssistantHtml } from '../lib/markdown'

const SIDEBAR_MIN = 240
// 3x the previous 560 cap so a sidebar can be pulled out to near-full-screen width
const SIDEBAR_MAX = 1680
const SIDEBAR_DEFAULT = 380

function loadSidebarWidth(key: string): number {
  const raw = localStorage.getItem(key)
  if (raw === null) return SIDEBAR_DEFAULT
  const n = parseInt(raw, 10)
  return isNaN(n) ? SIDEBAR_DEFAULT : Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, n))
}

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
// Top-level aliases: nested refs inside a plain object are NOT auto-unwrapped
const activeConversationId = chat.conversationId

const expandedReasoning = ref<Record<number, boolean>>({})
const messageInput = ref('')
const inputEl = ref<HTMLTextAreaElement | null>(null)
const attachedImage = ref<string | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

// Edit / branch state
const editingIndex = ref<number | null>(null)
const editingText = ref('')

// Sidebar tab switcher — persisted to localStorage
const activeTab = ref<'history' | 'chats'>(
  (localStorage.getItem('chat.sidebar.tab') as 'history' | 'chats') || 'history',
)

function setActiveTab(tab: 'history' | 'chats'): void {
  activeTab.value = tab
  localStorage.setItem('chat.sidebar.tab', tab)
}

// Refresh key for ChatsPanel — bumps when streaming ends
const chatsRefreshKey = ref(0)
watch(() => streaming.value, async (now, was) => {
  if (was && !now) {
    chatsRefreshKey.value++
    try {
      const detail = await getChat(activeConversationId.value!)
      if (detail.messages.length === messages.value.length) {
        detail.messages.forEach((m, i) => {
          const local = messages.value[i]
          local.id = m.id
          local.siblingIndex = m.sibling_index
          local.siblingCount = m.sibling_count
          local.prevSiblingId = m.prev_sibling_id
          local.nextSiblingId = m.next_sibling_id
        })
      }
    } catch { /* ignore — edit buttons stay hidden until next load */ }
  }
})

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

async function quickSend(action: { label: string; text: string }): Promise<void> {
  messageInput.value = action.text
  await sendMessage()
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

const leftWidth = ref(loadSidebarWidth('chat.sidebar.left.width'))
const rightWidth = ref(loadSidebarWidth('chat.sidebar.right.width'))

let draggingSide: 'left' | 'right' | null = null

function clamp(v: number): number {
  return Math.round(Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, v)))
}

function startResize(side: 'left' | 'right', _e: MouseEvent): void {
  if (isMobileLayout() || draggingSide) return
  draggingSide = side
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'
  window.addEventListener('mousemove', onResizeMove)
  window.addEventListener('mouseup', endResize)
}

function onResizeMove(e: MouseEvent): void {
  if (!draggingSide) return
  const rect = document.querySelector('.chat-page')?.getBoundingClientRect()
  if (!rect) return
  if (draggingSide === 'left') {
    leftWidth.value = clamp(e.clientX - rect.left)
  } else {
    rightWidth.value = clamp(rect.right - e.clientX)
  }
}

function endResize(): void {
  window.removeEventListener('mousemove', onResizeMove)
  window.removeEventListener('mouseup', endResize)
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
  if (draggingSide === 'left') {
    localStorage.setItem('chat.sidebar.left.width', String(leftWidth.value))
  } else if (draggingSide === 'right') {
    localStorage.setItem('chat.sidebar.right.width', String(rightWidth.value))
  }
  draggingSide = null
}

function resetWidth(side: 'left' | 'right'): void {
  if (side === 'left') {
    leftWidth.value = SIDEBAR_DEFAULT
    localStorage.removeItem('chat.sidebar.left.width')
  } else {
    rightWidth.value = SIDEBAR_DEFAULT
    localStorage.removeItem('chat.sidebar.right.width')
  }
}

onBeforeUnmount(() => {
  if (draggingSide) {
    window.removeEventListener('mousemove', onResizeMove)
    window.removeEventListener('mouseup', endResize)
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
    draggingSide = null
  }
})

onMounted(() => { void restoreLastConversation() })

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

// Diagnostic for the ticket gate UI: prefer the diag whose session matches
// the draft, else the latest diag in the visible chat.
const ticketDiag = computed<DiagnosticResult | null>(() => {
  const list = messages.value as (ChatMessage & { _diag?: DiagnosticResult })[]
  const sid = ticketDraft.value?.session_id
  for (let i = list.length - 1; i >= 0; i--) {
    const d = list[i]?._diag
    if (d && sid && d.session_id === sid) return d
  }
  for (let i = list.length - 1; i >= 0; i--) {
    const d = list[i]?._diag
    if (d) return d
  }
  return null
})

const historyRefreshKey = ref(0)

function handleTicketSubmitted(_ticketId: string): void {
  historyRefreshKey.value++
}
function handleTicketClose(): void { showTicketModal.value = false; ticketDraft.value = null }

async function handleNewDialog(): Promise<void> {
  if (!props.vehicleId) return
  chat.resetLocal()
}

async function handleSelectConversation(conversationId: string): Promise<void> {
  try {
    const detail = await getChat(conversationId)
    chat.loadConversation(detail)
    if (isMobileLayout()) mobilePanel.value = null
  } catch { /* keep current transcript on failure */ }
}

async function restoreLastConversation(): Promise<void> {
  if (!props.vehicleId) return
  try {
    const convs = await listChats(props.vehicleId)
    if (convs.length === 0) return
    const detail = await getChat(convs[0].id)
    // User may have started typing/sending while we fetched — don't clobber.
    if (messages.value.length > 0 || streaming.value) return
    chat.loadConversation(detail)
  } catch { /* start with an empty chat on failure */ }
}

function handleConversationDeleted(deletedId: string): void {
  if (activeConversationId.value === deletedId) chat.resetLocal()
}

// ---------------------------------------------------------------------------
// Edit / branch helpers
// ---------------------------------------------------------------------------

function startEdit(idx: number): void {
  if (streaming.value) return
  editingIndex.value = idx
  editingText.value = messages.value[idx].text
}

function cancelEdit(): void {
  editingIndex.value = null
  editingText.value = ''
}

async function saveEdit(idx: number): Promise<void> {
  const text = editingText.value.trim()
  if (!text) return
  editingIndex.value = null
  try {
    await chat.editMessage(props.vehicleId, idx, text)
  } catch { /* keep current transcript on failure */ }
}

async function switchBranch(messageId: number | null | undefined): Promise<void> {
  if (!messageId || streaming.value || !activeConversationId.value) return
  try {
    const detail = await switchChatBranch(activeConversationId.value, messageId)
    expandedReasoning.value = {}
    chat.loadConversation(detail)
  } catch { /* keep current transcript on failure */ }
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
    <aside v-show="leftOpen" class="chat-sidebar left" :style="{ width: leftWidth + 'px' }">
      <div class="sidebar-tabs">
        <button :class="['sidebar-tab', { active: activeTab === 'history' }]" @click="setActiveTab('history')">{{ t('history.title') }}</button>
        <button :class="['sidebar-tab', { active: activeTab === 'chats' }]" @click="setActiveTab('chats')">{{ t('chats.tab') }}</button>
      </div>
      <button class="new-dialog-btn" :disabled="streaming" @click="handleNewDialog">{{ t('chat.new_dialog') }}</button>
      <HistoryPanel v-show="activeTab === 'history'" :vehicle-id="props.vehicleId" :refresh-key="historyRefreshKey" />
      <ChatsPanel
        v-if="activeTab === 'chats'"
        :vehicle-id="props.vehicleId"
        :active-id="activeConversationId"
        :refresh-key="chatsRefreshKey"
        :disabled="streaming"
        @select="handleSelectConversation"
        @deleted="handleConversationDeleted"
      />
      <div class="sidebar-resizer" @mousedown="startResize('left', $event)" @dblclick="resetWidth('left')" role="separator" aria-orientation="vertical" />
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
        <button class="back-btn" @click="emit('back')">
          <svg class="back-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/>
          </svg>
          {{ t('chat.back') }}
        </button>
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
                  <svg :class="{ chevron: true, open: !!expandedReasoning[idx] }" class="chevron-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M9 18l6-6-6-6"/>
                  </svg>
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
            <!-- Editing mode -->
            <template v-if="editingIndex === idx">
              <div class="bubble user-bubble edit-mode">
                <textarea
                  class="edit-textarea"
                  v-model="editingText"
                  rows="3"
                  @keydown.enter.exact.prevent="saveEdit(idx)"
                  @keydown.escape="cancelEdit()"
                ></textarea>
                <div class="edit-actions">
                  <button class="edit-action-btn save" @click="saveEdit(idx)">{{ t('chat.edit.save') }}</button>
                  <button class="edit-action-btn cancel" @click="cancelEdit()">{{ t('chat.edit.cancel') }}</button>
                </div>
              </div>
            </template>
            <!-- Normal mode -->
            <template v-else>
              <div class="user-bubble-wrap">
                <div class="bubble user-bubble" style="position:relative;">
                  <img v-if="msg.image" :src="msg.image" class="user-image-thumb" />
                  {{ msg.text }}
                  <!-- Edit button -->
                  <button
                    v-if="msg.id !== undefined && !streaming"
                    class="edit-btn"
                    :title="t('chat.edit.label')"
                    @click="startEdit(idx)"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                      <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
                    </svg>
                  </button>
                </div>
                <!-- Branch switcher -->
                <div v-if="msg.siblingCount && msg.siblingCount > 1" class="branch-switcher">
                  <button :disabled="!msg.prevSiblingId || streaming" @click="switchBranch(msg.prevSiblingId!)">‹</button>
                  <span>{{ msg.siblingIndex }}/{{ msg.siblingCount }}</span>
                  <button :disabled="!msg.nextSiblingId || streaming" @click="switchBranch(msg.nextSiblingId!)">›</button>
                </div>
              </div>
            </template>
          </template>
        </div>

        <div v-if="streaming" class="streaming-indicator">
          <span class="spinner" /><span class="dim">{{ t('chat.streaming') }}</span>
        </div>

        <!-- Quick actions: centered in the chat area when empty with vehicle -->
        <div v-if="!streaming && messages.length === 0 && vehicleId" class="quick-actions">
          <button v-for="action in quickActions" :key="action.label" class="quick-chip" @click="quickSend(action)">{{ action.label }}</button>
        </div>

        <!-- Empty vehicle banner: centered when no vehicle selected -->
        <div v-if="!vehicleId && !streaming" class="chat-empty-banner panel">
          <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          <span>{{ t('chat.empty_vehicle') }}</span>
        </div>
      </div>

      <div class="input-row" v-if="vehicleId">
        <div v-if="attachedImage" class="image-preview-chip">
          <img :src="attachedImage" alt="" class="preview-thumb" />
          <button class="remove-btn" @click="attachedImage = null" :title="t('chat.attach.remove')">&times;</button>
        </div>
        <textarea v-model="messageInput" rows="1" :placeholder="t('chat.input.placeholder')" :disabled="streaming || !vehicleId" @keydown="onKeydown" @input="autoGrow" />
        <input type="file" accept="image/*" ref="fileInput" style="display:none" @change="onFileSelected" />
        <div class="composer-tools">
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
          <div class="composer-tools-right">
            <button
              v-if="micSupported && !streaming && vehicleId"
              class="mic-btn"
              :class="{ listening: micListening }"
              :title="micListening ? t('chat.mic.listening') : t('chat.mic.label')"
              :aria-label="micListening ? t('chat.mic.listening') : t('chat.mic.label')"
              @click="toggleMic"
            >
              <svg class="mic-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                <line x1="12" y1="19" x2="12" y2="22"/>
              </svg>
            </button>
            <button v-if="!streaming" class="send-btn primary" :disabled="!messageInput.trim() || !vehicleId" @click="sendMessage"><svg class="send-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M12 19V5"/><path d="M5 12l7-7 7 7"/>
            </svg></button>
            <button v-else class="stop-btn danger-solid" @click="chat.stop">{{ t('chat.stop') }}</button>
          </div>
        </div>
      </div>
      </div>

      <aside v-show="rightOpen" class="chat-sidebar right" :style="{ width: rightWidth + 'px' }">
        <DocPanel v-if="activeDocId" :doc-id="activeDocId" :page="activePage" />
        <div v-else class="panel-empty dim">{{ t('chat.select_doc') }}</div>
        <div class="sidebar-resizer" @mousedown="startResize('right', $event)" @dblclick="resetWidth('right')" role="separator" aria-orientation="vertical" />
      </aside>

      <div v-if="mobilePanel === 'history'" class="mobile-overlay" @click.self="mobilePanel = null">
        <div class="mobile-panel-header">
          <h3>{{ t('chat.history') }}</h3>
          <button class="close-btn" @click="mobilePanel = null">&times;</button>
        </div>
        <div class="mobile-panel-body">
          <div class="sidebar-tabs">
            <button :class="['sidebar-tab', { active: activeTab === 'history' }]" @click="setActiveTab('history')">{{ t('history.title') }}</button>
            <button :class="['sidebar-tab', { active: activeTab === 'chats' }]" @click="setActiveTab('chats')">{{ t('chats.tab') }}</button>
          </div>
          <HistoryPanel v-show="activeTab === 'history'" :vehicle-id="props.vehicleId" :refresh-key="historyRefreshKey" />
          <ChatsPanel
            v-if="activeTab === 'chats'"
            :vehicle-id="props.vehicleId"
            :active-id="activeConversationId"
            :refresh-key="chatsRefreshKey"
            :disabled="streaming"
            @select="handleSelectConversation"
            @deleted="handleConversationDeleted"
          />
        </div>
      </div>

      <div v-if="mobilePanel === 'doc'" class="mobile-overlay" @click.self="mobilePanel = null">
        <div class="mobile-panel-header">
          <h3>{{ t('chat.document') }}</h3>
          <button class="close-btn" @click="mobilePanel = null">&times;</button>
        </div>
        <DocPanel :doc-id="activeDocId!" :page="activePage" />
      </div>

    <AppModal v-if="showTicketModal && ticketDraft" wide title="Заявка на дефектовку" @close="handleTicketClose">
      <TicketForm :draft="ticketDraft" :vehicle-id="props.vehicleId" :diag="ticketDiag" @submitted="handleTicketSubmitted" @close="handleTicketClose" />
    </AppModal>
  </div>
</template>

<style scoped>
.chat-page { display: flex; flex-direction: row; flex: 1; min-height: 0; overflow: hidden; }
.chat-header { display: flex; align-items: center; gap: 12px; padding: 8px 12px; margin-bottom: 0; border-radius: 0; flex-shrink: 0; min-width: 0; }
.back-btn { display: inline-flex; align-items: center; gap: 4px; background: transparent; border: 0; color: var(--text-dim); font-size: 13px; padding: 4px 8px; cursor: pointer; flex-shrink: 0; }
.back-icon { width: 14px; height: 14px; }
.back-btn:hover { color: var(--accent); }
.header-info { flex: 1; min-width: 0; }
.header-main { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.garage-badge { background: var(--accent-dim); color: var(--text-on-accent); padding: 2px 8px; border-radius: var(--radius-sm); font-size: 12px; font-weight: 700; flex-shrink: 0; }
.vehicle-name { overflow: hidden; text-overflow: ellipsis; }
.header-meta { display: flex; align-items: center; gap: 6px; margin-top: 2px; }
.engine-chip { background: var(--bg-input); border: 1px solid var(--border); color: var(--text-dim); padding: 1px 8px; border-radius: 999px; font-size: 11px; }
.chat-column { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.chat-sidebar { width: 380px; flex-shrink: 0; display: flex; flex-direction: column; overflow-y: auto; overflow-x: hidden; background: var(--bg-panel); position: relative; }
.chat-sidebar.left { border-right: 1px solid var(--border); }
.chat-sidebar.right { border-left: 1px solid var(--border); }
.sidebar-resizer { position: absolute; top: 0; bottom: 0; width: 6px; cursor: col-resize; z-index: 10; }
.chat-sidebar.left .sidebar-resizer { right: 0; }
.chat-sidebar.right .sidebar-resizer { left: 0; }
.sidebar-resizer:hover { background: var(--accent-dim); opacity: 0.4; }
.chat-sidebar > * { flex-shrink: 0; }
.sidebar-tabs { display: flex; gap: 4px; margin: 12px 12px 0; }
.sidebar-tab { flex: 1; background: transparent; border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 6px 8px; font-size: 12px; color: var(--text-dim); cursor: pointer; min-height: 32px; }
.sidebar-tab.active { color: var(--accent); border-color: var(--accent); background: var(--bg-input); font-weight: 600; }
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
.input-row { display: flex; flex-direction: column; gap: 6px; margin: 8px 16px 12px; padding: 10px 12px; background: var(--bg-panel); border: 1px solid var(--border); border-radius: 14px; box-shadow: 0 6px 24px rgba(0,0,0,0.35); flex-shrink: 0; }
.input-row:focus-within { border-color: var(--accent-dim); }
.input-row textarea { background: transparent; border: 0; padding: 8px 10px; min-height: 40px; max-height: 120px; font-size: 14px; font-family: inherit; resize: none; width: 100%; }
.composer-tools { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.composer-tools-right { display: flex; align-items: center; gap: 6px; }
.send-btn { width: 44px; height: 44px; border-radius: 50%; font-size: 20px; display: flex; align-items: center; justify-content: center; padding: 0; flex-shrink: 0; }
.stop-btn { height: 44px; width: auto; min-width: 64px; border-radius: 999px; padding: 0 16px; display: flex; align-items: center; justify-content: center; font-size: 13px; flex-shrink: 0; }
.attach-btn { width: 36px; height: 36px; border-radius: 50%; background: transparent; border: 0; color: var(--text-dim); display: flex; align-items: center; justify-content: center; padding: 0; cursor: pointer; flex-shrink: 0; }
  .attach-btn:hover { background: var(--bg-input); color: var(--accent); }
.attach-icon { width: 20px; height: 20px; }
.send-icon { width: 20px; height: 20px; }
.mic-btn { width: 44px; height: 44px; border-radius: 50%; background: transparent; border: 0; color: var(--text-dim); display: flex; align-items: center; justify-content: center; padding: 0; cursor: pointer; flex-shrink: 0; }
  .mic-btn:hover { background: var(--bg-input); color: var(--accent); }
.mic-icon { width: 22px; height: 22px; }
@keyframes mic-pulse { 0%, 100% { opacity: 1; box-shadow: none; } 50% { opacity: 0.6; box-shadow: 0 0 8px var(--accent); } }
.image-preview-chip { display: flex; align-items: center; gap: 8px; padding: 2px 2px 4px; background: transparent; border-top: 0; flex-shrink: 0; }
.preview-thumb { width: 48px; height: 48px; object-fit: cover; border-radius: var(--radius-sm); border: 1px solid var(--border); }
.remove-btn { background: transparent; border: none; color: var(--danger-text); font-size: 20px; line-height: 1; cursor: pointer; padding: 4px 8px; flex-shrink: 0; }
.user-image-thumb { max-width: 100%; max-height: 160px; border-radius: var(--radius-sm); margin-bottom: 8px; display: block; object-fit: contain; }
.mic-btn.listening { color: var(--accent); }
  .mic-btn.listening .mic-icon { animation: mic-pulse 1s ease-in-out infinite; }
.chat-error { position: relative; margin: 8px 16px 0; }
.close-error { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: none; border: 0; color: var(--danger-text); font-size: 16px; padding: 4px; cursor: pointer; }
.panel-empty { padding: 24px; text-align: center; }
/* Full-screen sheet: opaque page surface. var(--overlay) is translucent and
   meant for modal backdrops — with it the topbar (locale chip, nav) bleeds
   through the transparent panel body right at the tab row. */
.mobile-overlay { position: fixed; inset: 0; background: var(--bg); z-index: 150; display: flex; flex-direction: column; }
.mobile-panel-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; background: var(--bg-panel); border-bottom: 1px solid var(--border); flex-shrink: 0; }
.mobile-overlay > .mobile-panel-body { flex: 1; min-height: 0; overflow-y: auto; -webkit-overflow-scrolling: touch; }
.close-btn { background: none; border: 0; color: var(--text-dim); font-size: 24px; padding: 0 4px; cursor: pointer; }
@media (max-width: 1023px) { .chat-sidebar { display: none; } }
@media (min-width: 1024px) { .mobile-overlay { display: none; } }
@media (max-width: 640px) {
  .chat-header { flex-wrap: wrap; row-gap: 4px; }
  .header-info { order: -1; flex-basis: 100%; }
  .input-row { margin: 8px 8px 10px; }
}
.reasoning-toggle { background: transparent; border: 0; color: var(--text-dim); font-size: 11px; cursor: pointer; padding: 0 2px; line-height: 1.2; display: inline-flex; align-items: center; gap: 4px; }
.reasoning-toggle:hover { color: var(--accent); }
.chevron { display: inline-block; transition: transform 0.15s ease; width: 12px; height: 12px; }
.chevron.open { transform: rotate(90deg); }
.reasoning-body { color: var(--text-dim); font-size: 12px; white-space: pre-wrap; max-height: 180px; overflow-y: auto; margin: 4px 0; line-height: 1.4; }

/* Edit / branch */
.edit-btn { position: absolute; top: 4px; right: 4px; width: 22px; height: 22px; background: transparent; border: 0; color: var(--text-dim); cursor: pointer; display: flex; align-items: center; justify-content: center; border-radius: 4px; opacity: 0; transition: opacity 0.15s ease, color 0.15s ease; }
.message-row.user:hover .edit-btn { opacity: 1; }
.edit-btn:hover { color: var(--accent); background: var(--bg-input); }
.edit-btn:focus { opacity: 1; outline: 1px solid var(--accent); }
.edit-btn svg { width: 14px; height: 14px; }
.user-bubble-wrap { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
.edit-textarea { background: transparent; border: 0; padding: 8px 10px; min-height: 60px; max-height: 200px; font-size: 14px; font-family: inherit; resize: vertical; width: 100%; color: var(--text-on-accent); }
.edit-textarea:focus { outline: 1px solid var(--accent); border-radius: var(--radius-sm); }
.edit-actions { display: flex; gap: 6px; justify-content: flex-end; margin-top: 4px; }
.edit-action-btn { font-size: 12px; padding: 3px 10px; border-radius: var(--radius-sm); cursor: pointer; border: 1px solid var(--border); background: transparent; color: var(--text-dim); }
.edit-action-btn.save:hover { background: var(--accent-dim); color: var(--text-on-accent); border-color: var(--accent); }
.edit-action-btn.cancel:hover { color: var(--danger-text); border-color: var(--danger-text); }
.branch-switcher { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--text-dim); }
.branch-switcher button { background: transparent; border: 0; color: var(--text-dim); cursor: pointer; padding: 2px 4px; font-size: 11px; line-height: 1; border-radius: 3px; }
.branch-switcher button:hover:not(:disabled) { color: var(--accent); background: var(--bg-input); }
.branch-switcher button:disabled { opacity: 0.35; cursor: default; }
</style>
