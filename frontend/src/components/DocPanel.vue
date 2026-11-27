<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { fetchDocumentFile } from '../api'
import { t } from '../i18n'

// pdf.js loads lazily (dynamic import inside loadDocument) so the main bundle
// stays lean; only the worker asset URL and text-layer CSS are static.
import type {
  PDFDocumentLoadingTask,
  PDFDocumentProxy,
  PDFPageProxy,
  RenderTask,
  TextLayer,
} from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import 'pdfjs-dist/web/pdf_viewer.css'

// ---------------------------------------------------------------------------
// Props & state
// ---------------------------------------------------------------------------

const props = defineProps<{
  docId: string | null
  page: number | null
}>()

type PdfJsModule = typeof import('pdfjs-dist')

let pdfjs: PdfJsModule | null = null
let pdfDoc: PDFDocumentProxy | null = null
let loadingTask: PDFDocumentLoadingTask | null = null
const canvasRef = ref<HTMLCanvasElement | null>(null)
const textLayerDivRef = ref<HTMLDivElement | null>(null)

// Current page being displayed (1-based)
const currentPage = ref(1)
// Total pages (set after document loads)
const numPages = ref(0)
// Scale factor
let scale = 1
// Loading / error state
const loading = ref(false)
const error = ref<string | null>(null)

// Track in-flight render tasks for cancellation
let currentRenderTask: RenderTask | null = null
let currentTextLayer: TextLayer | null = null

// Container width measurement
const containerEl = ref<HTMLDivElement | null>(null)
const containerWidth = ref<number>(0)

// Fit-width mode: the page scale tracks the container (sidebar) width until
// the user zooms manually, then their scale wins.
let fitMode = true
let resizeObserver: ResizeObserver | null = null
let refitTimer: number | null = null

// ---------------------------------------------------------------------------
// Computed page title (page / numPages)
// ---------------------------------------------------------------------------
const pageTitle = computed(() => t('doc.page.title', { n: String(currentPage.value), m: String(numPages.value) }))

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function clampScale(v: number): number {
  return Math.min(3.0, Math.max(0.4, v))
}

// Fit-width may exceed the manual zoom cap: with a wide sidebar the page must
// still fill the available width.
function clampFitScale(v: number): number {
  return Math.min(6.0, Math.max(0.2, v))
}

function getDPR(): number {
  return window.devicePixelRatio ?? 1
}

/** Calculate initial scale to fit width of container. */
function computeInitialScale(page: PDFPageProxy): number {
  const vp = page.getViewport({ scale: 1 })
  let w = containerWidth.value
  if (w <= 0) w = 360 // fallback
  return clampFitScale(w / vp.width)
}

/** Recompute the fit-width scale for the current page and re-render if it changed. */
async function refitToWidth(): Promise<void> {
  if (!pdfDoc || containerWidth.value <= 0) return
  const page = await pdfDoc.getPage(currentPage.value)
  const vp = page.getViewport({ scale: 1 })
  const next = clampFitScale(containerWidth.value / vp.width)
  if (Math.abs(next - scale) < 0.005) return // below render noise
  scale = next
  await renderPage()
}

// Debounced so a sidebar drag re-renders once on settle, not per mousemove.
function scheduleRefit(): void {
  if (refitTimer !== null) clearTimeout(refitTimer)
  refitTimer = window.setTimeout(() => { refitTimer = null; void refitToWidth() }, 150)
}

/** Cancel in-flight render and text-layer tasks. */
function cancelInflightTasks(): void {
  if (currentRenderTask) {
    try { currentRenderTask.cancel() } catch { /* ignore */ }
    currentRenderTask = null
  }
  if (currentTextLayer) {
    try { currentTextLayer.cancel() } catch { /* ignore */ }
    currentTextLayer = null
  }
}

/** Render the current page at the current scale. */
async function renderPage(): Promise<void> {
  if (!pdfDoc || !pdfjs || !canvasRef.value || !textLayerDivRef.value) return

  const pageNum = currentPage.value
  if (pageNum < 1 || pageNum > pdfDoc.numPages) return

  cancelInflightTasks()

  const canvas = canvasRef.value
  const textLayerDiv = textLayerDivRef.value
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const page = await pdfDoc.getPage(pageNum)
  const viewportRaw = page.getViewport({ scale })
  const dpr = getDPR()

  // Size canvas for DPR
  canvas.width = Math.floor(viewportRaw.width * dpr)
  canvas.height = Math.floor(viewportRaw.height * dpr)
  canvas.style.width = `${viewportRaw.width}px`
  canvas.style.height = `${viewportRaw.height}px`

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

  // Set CSS variables for text layer
  const wrapper = canvas.parentElement
  if (wrapper) {
    wrapper.style.setProperty('--scale-factor', String(scale))
    wrapper.style.setProperty('--total-scale-factor', String(scale))
  }

  // Render PDF page
  currentRenderTask = page.render({ canvas, canvasContext: ctx, viewport: viewportRaw })
  try {
    await currentRenderTask
  } catch (err: unknown) {
    if ((err as { name?: string })?.name === 'RenderingCancelledException') return
    throw err
  }

  // TextLayer does not clear its container — drop spans from any previous render.
  textLayerDiv.replaceChildren()

  // Render text layer
  const textContentSource = page.streamTextContent()
  currentTextLayer = new pdfjs.TextLayer({
    textContentSource,
    container: textLayerDiv,
    viewport: viewportRaw,
  })
  try {
    await currentTextLayer.render()
  } catch (err: unknown) {
    if ((err as { name?: string })?.name === 'RenderingCancelledException') return
    throw err
  }
}

// ---------------------------------------------------------------------------
// Load PDF document
// ---------------------------------------------------------------------------

async function loadDocument(): Promise<void> {
  if (!props.docId) return

  cancelInflightTasks()
  loading.value = true
  error.value = null
  pdfDoc = null
  numPages.value = 0

  try {
    if (!pdfjs) {
      pdfjs = await import('pdfjs-dist')
      pdfjs.GlobalWorkerOptions.workerSrc = workerUrl
    }
    const data = await fetchDocumentFile(props.docId)
    loadingTask = pdfjs.getDocument({ data })
    pdfDoc = await loadingTask.promise

    // Guard: clamp page to loaded doc range
    if (props.page !== null) {
      currentPage.value = Math.max(1, Math.min(pdfDoc.numPages, props.page))
    } else {
      currentPage.value = 1
    }
    numPages.value = pdfDoc.numPages

    const firstPage = await pdfDoc.getPage(1)

    // Reveal the viewer before measuring: the container only exists once
    // loading is false, and fit-width needs its rendered width.
    loading.value = false
    await nextTick()
    measureContainerWidth()
    scale = computeInitialScale(firstPage)

    await renderPage()
  } catch (e: unknown) {
    loading.value = false
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
      error.value = t('doc.error.generic', { msg: String(e) })
    }
  }
}

// Track container width changes (sidebar resize / panel reopen). Fires once on
// observe() too, which keeps containerWidth fresh for the initial fit.
watch(containerEl, (el) => {
  if (resizeObserver) { resizeObserver.disconnect(); resizeObserver = null }
  if (!el) return
  resizeObserver = new ResizeObserver((entries) => {
    const w = entries[0]?.contentRect.width ?? 0
    // While the sidebar is hidden (display:none) the width reads as 0 — keep
    // the last known value so a hidden panel doesn't reset the fit.
    if (w > 0) containerWidth.value = w
    if (fitMode && w > 0) scheduleRefit()
  })
  resizeObserver.observe(el)
})

// ---------------------------------------------------------------------------
// Watchers
// ---------------------------------------------------------------------------

watch(
  () => props.docId,
  async () => {
    cancelInflightTasks()
    if (loadingTask) { loadingTask.destroy(); loadingTask = null }
    pdfDoc = null
    // Reset state for new doc
    currentPage.value = 1
    numPages.value = 0
    scale = 1
    fitMode = true
    loading.value = false
    error.value = null
    await loadDocument()
  },
  { immediate: true },
)

watch(
  () => props.page,
  (newPage) => {
    if (!pdfDoc) {
      // Document not loaded yet — page will be applied after load via docId watcher
      return
    }
    if (newPage === null) return
    const clamped = Math.max(1, Math.min(pdfDoc.numPages, newPage))
    if (clamped !== currentPage.value) {
      currentPage.value = clamped
      renderPage()
    }
  },
)

// ---------------------------------------------------------------------------
// Toolbar actions
// ---------------------------------------------------------------------------

function goPrev(): void {
  if (currentPage.value <= 1) return
  currentPage.value--
  renderPage()
}

function goNext(): void {
  if (!pdfDoc || currentPage.value >= pdfDoc.numPages) return
  currentPage.value++
  renderPage()
}

function zoomIn(): void {
  fitMode = false
  scale = clampScale(scale * 1.2)
  renderPage()
}

function zoomOut(): void {
  fitMode = false
  scale = clampScale(scale / 1.2)
  renderPage()
}

// ---------------------------------------------------------------------------
// Container width measurement
// ---------------------------------------------------------------------------

function measureContainerWidth(): void {
  const el = containerEl.value
  if (!el) return
  // Subtract padding from the wrapper to get usable width
  const rect = el.getBoundingClientRect()
  containerWidth.value = Math.max(0, rect.width - 16) // ~8px padding each side
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onBeforeUnmount(() => {
  cancelInflightTasks()
  if (resizeObserver) { resizeObserver.disconnect(); resizeObserver = null }
  if (refitTimer !== null) { clearTimeout(refitTimer); refitTimer = null }
  if (loadingTask) { loadingTask.destroy(); loadingTask = null }
  pdfDoc = null
})
</script>

<template>
  <div class="doc-panel panel">
    <!-- Page indicator toolbar -->
    <div v-if="numPages > 0 && !loading" class="toolbar">
      <button
        class="tool-btn"
        :disabled="currentPage <= 1"
        :aria-label="t('doc.prev_page')"
        @click="goPrev"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path d="M15 18l-6-6 6-6"/>
        </svg>
      </button>

      <span class="page-indicator">{{ pageTitle }}</span>

      <button
        class="tool-btn"
        :disabled="currentPage >= numPages"
        :aria-label="t('doc.next_page')"
        @click="goNext"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path d="M9 18l6-6-6-6"/>
        </svg>
      </button>

      <span class="toolbar-sep" />

      <button
        class="tool-btn"
        :aria-label="t('doc.zoom_out')"
        @click="zoomOut"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path d="M5 12h14"/>
        </svg>
      </button>

      <button
        class="tool-btn"
        :aria-label="t('doc.zoom_in')"
        @click="zoomIn"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path d="M12 5v14M5 12h14"/>
        </svg>
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="doc-loading">
      <span class="spinner" />
      <span class="dim">{{ t('doc.loading') }}</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="error-strip" role="alert">
      {{ error }}
    </div>

    <!-- PDF viewer container -->
    <div
      v-else-if="!loading && !error"
      ref="containerEl"
      class="pdf-viewer"
    >
      <div class="pdf-page">
        <canvas ref="canvasRef" />
        <div ref="textLayerDivRef" class="textLayer" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}

.tool-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-dim);
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.tool-btn:hover:not(:disabled) {
  color: var(--text);
  border-color: var(--accent);
}

.tool-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.page-indicator {
  font-size: 13px;
  color: var(--text-dim);
  min-width: 80px;
  text-align: center;
  user-select: none;
}

.toolbar-sep {
  width: 1px;
  height: 20px;
  background: var(--border);
  margin: 0 4px;
}

.pdf-viewer {
  overflow: auto;
  display: flex;
  justify-content: center;
  padding: 8px;
  max-height: calc(100vh - 200px);
}

.pdf-page {
  position: relative;
  display: inline-block;
  --scale-factor: 1;
  --total-scale-factor: 1;
}

.pdf-page canvas {
  display: block;
  border: none;
}

/* The .textLayer itself is styled entirely by pdfjs-dist's pdf_viewer.css
   (absolute overlay, transparent spans, ::selection highlight). */

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
</style>
