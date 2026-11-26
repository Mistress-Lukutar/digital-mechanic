<script setup lang="ts">
import { ref, watch } from 'vue'
import { getDocumentPage, apiUrl } from '../api'
import { t } from '../i18n'

const props = defineProps<{
  docId: string | null
  page: number | null
}>()

const pageTitle = ref('')
const pageText = ref('')
const loading = ref(false)
const error = ref<string | null>(null)

async function loadPage(): Promise<void> {
  if (!props.docId || props.page === null) return

  loading.value = true
  error.value = null
  pageTitle.value = ''
  pageText.value = ''

  try {
    const data = await getDocumentPage(props.docId, props.page)
    pageTitle.value = data.doc_title
    pageText.value = data.text || ''
  } catch (e: unknown) {
    if (e instanceof Error && 'status' in e) {
      const status = (e as { status: number }).status
      if (status === 404) {
        error.value = t('doc.error.unavailable')
      } else {
        error.value = t('doc.error.generic', { msg: e.message })
      }
    } else if (e instanceof Error) {
      error.value = e.message
    } else {
      error.value = t('doc.error.load')
    }
  } finally {
    loading.value = false
  }
}

watch(() => [props.docId, props.page], loadPage, { immediate: true })

function openPdf(): void {
  if (!props.docId || props.page === null) return
  const url = apiUrl(`/api/documents/${encodeURIComponent(props.docId)}/file`) + `#page=${props.page}`
  window.open(url, '_blank')
}
</script>

<template>
  <div class="doc-panel panel">
    <!-- Header -->
    <h3 v-if="pageTitle" class="doc-title">{{ pageTitle }} — {{ t('doc.page.title', { n: String(props.page) }) }}</h3>

    <!-- Loading -->
    <div v-if="loading" class="doc-loading">
      <span class="spinner" />
      <span class="dim">{{ t('doc.loading') }}</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="error-strip" role="alert">
      {{ error }}
    </div>

    <!-- Content -->
    <template v-else>
      <pre v-if="pageText" class="doc-text">{{ pageText }}</pre>

      <p v-else class="dim">{{ t('doc.empty') }}</p>

      <button v-if="docId && page !== null" class="primary mt-8" @click="openPdf">
        {{ t('doc.open_pdf', { n: String(page) }) }}
      </button>
    </template>
  </div>
</template>

<style scoped>
.doc-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--text);
}

.doc-loading {
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

.doc-text {
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text);
  margin: 0;
  max-height: 400px;
  overflow-y: auto;
  padding: 8px;
  background: var(--bg-input);
  border-radius: var(--radius-sm);
}

.mt-8 {
  margin-top: 8px;
}
</style>
