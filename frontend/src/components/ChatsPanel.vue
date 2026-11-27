<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import type { ChatConversationItem } from '../types'
import { listChats, deleteChat, formatIso } from '../api'
import { t } from '../i18n'
import { useConfirm } from '../composables/useConfirm'

const props = defineProps<{
  vehicleId: string
  /** Currently loaded conversation ID (for highlighting). */
  activeId: string | null
  /** Bump to re-read the chat list. */
  refreshKey?: number
  /** When true, suppress select and delete actions. */
  disabled?: boolean
}>()

const emit = defineEmits<{
  select: [conversationId: string]
  deleted: [conversationId: string]
}>()

const { confirm } = useConfirm()

const conversations = ref<ChatConversationItem[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

async function load(): Promise<void> {
  if (!props.vehicleId) return
  loading.value = true
  try {
    const data = await listChats(props.vehicleId)
    conversations.value = data ?? []
  } catch (e: unknown) {
    if (e instanceof Error) {
      error.value = e.message
    } else {
      error.value = t('chats.loading')
    }
  } finally {
    loading.value = false
  }
}

watch(() => props.refreshKey, (key) => {
  if (key) load()
})

onMounted(load)

async function handleDelete(id: string): Promise<void> {
  if (props.disabled) return
  const accepted = await confirm({
    title: t('chats.delete'),
    message: t('chats.delete_confirm'),
    danger: true,
  })
  if (!accepted) return
  try {
    await deleteChat(id)
    emit('deleted', id)
    load()
  } catch { /* keep existing list on failure */ }
}
</script>

<template>
  <div class="chats-panel panel">
    <h3>{{ t('chats.tab') }}</h3>

    <!-- Loading -->
    <div v-if="loading" class="chats-loading">
      <span class="spinner" />
      <span class="dim">{{ t('chats.loading') }}</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="error-strip">
      {{ error }}
    </div>

    <!-- Empty / items -->
    <template v-else>
      <div v-if="conversations.length === 0" class="empty-hint dim">
        {{ t('chats.empty') }}
      </div>

      <div v-else class="chat-list">
        <div
          v-for="c in conversations" :key="c.id"
          :class="[
            'chat-item',
            { active: c.id === activeId },
            { disabled: props.disabled },
          ]"
          @click="!props.disabled && emit('select', c.id)"
        >
          <div class="chat-item-main">
            <span class="chat-title">{{ c.title || t('chats.untitled') }}</span>
            <div class="chat-meta">
              <span class="meta-date dim mono">{{ formatIso(c.updated_at) }}</span>
              <span class="meta-count dim mono">{{ c.message_count }}</span>
            </div>
          </div>
          <button
            v-if="!props.disabled"
            class="chat-delete-btn"
            :title="t('chats.delete')"
            @click.stop="handleDelete(c.id)"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M3 6h18"/>
              <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
              <path d="M10 11v6"/>
              <path d="M14 11v6"/>
            </svg>
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.chats-panel {
  padding: 12px;
}

.chats-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 0;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-hint {
  font-size: 13px;
  padding: 8px 0;
}

.chat-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.chat-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s;
}

.chat-item:hover:not(.disabled) {
  background: var(--bg-input);
}

.chat-item.active {
  background: var(--bg-input);
  border-left: 2px solid var(--accent);
  padding-left: 6px;
}

.chat-item.disabled {
  opacity: 0.5;
  cursor: default;
}

.chat-item-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.chat-title {
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text);
}

.chat-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}

.meta-date {
  color: var(--text-dim);
}

.meta-count {
  background: var(--bg-input);
  border: 1px solid var(--border);
  padding: 0 5px;
  border-radius: 4px;
  font-size: 10px;
  color: var(--text-dim);
}

.chat-delete-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 0;
  color: var(--text-dim);
  cursor: pointer;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.15s, visibility 0.15s;
}

.chat-item:hover .chat-delete-btn {
  opacity: 1;
  visibility: visible;
}

/* Touch devices have no hover — keep the delete action reachable. */
@media (hover: none) {
  .chat-delete-btn {
    opacity: 1;
    visibility: visible;
  }
}

.chat-delete-btn:hover {
  background: var(--bg-input);
  color: var(--danger-text);
}

.chat-delete-btn svg {
  width: 16px;
  height: 16px;
}
</style>
