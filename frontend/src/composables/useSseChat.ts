import { ref } from 'vue'
import { getAuthToken, apiUrl, formatApiDetail } from '../api'
import { locale, t } from '../i18n'
import type {
  AgentStepT,
  ChatMessage,
  DiagnosticResult,
  TicketDraftEvent,
} from '../types'

// ---------------------------------------------------------------------------
// SSE frame parser (handles partial frames, buffer-based)
// ---------------------------------------------------------------------------

interface SseFrame {
  event: string
  data: string
}

function parseSseFrames(raw: string): SseFrame[] {
  const frames: SseFrame[] = []
  // Split on double newlines (frame boundary in SSE)
  const parts = raw.split('\n\n')
  for (const part of parts) {
    const trimmed = part.trimEnd()
    if (!trimmed) continue
    let event = ''
    let data = ''
    for (const line of trimmed.split('\n')) {
      if (line.startsWith('event:')) {
        event = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        data = line.slice(5).trim()
      }
    }
    // If no explicit event, SSE spec says it defaults to "message"
    if (!event) event = 'message'
    if (data) frames.push({ event, data })
  }
  return frames
}

// ---------------------------------------------------------------------------
// Options passed into the composable factory
// ---------------------------------------------------------------------------

export interface SseChatOptions {
  onTicketDraft: (draft: TicketDraftEvent) => void
  onDocument: (docId: string, page: number) => void
}

// ---------------------------------------------------------------------------
// Diagnostic result parser (from tool_result content JSON)
// ---------------------------------------------------------------------------

function parseDiagnosticResult(content: string): DiagnosticResult | null {
  try {
    const obj = JSON.parse(content) as Record<string, unknown>
    return {
      status: String(obj.status ?? ''),
      anomaly_type: obj.anomaly_type ? String(obj.anomaly_type) : null,
      anomaly_title: obj.anomaly_title ? String(obj.anomaly_title) : null,
      anomaly_score:
        typeof obj.anomaly_score === 'number' ? obj.anomaly_score : null,
      confidence:
        typeof obj.confidence === 'number' ? obj.confidence : null,
      signal_quality: String(obj.signal_quality ?? ''),
      description: String(obj.description ?? ''),
      session_id: String(obj.session_id ?? ''),
      model_version: String(obj.model_version ?? ''),
    }
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------------
// Factory — returns a per-instance chat controller
// ---------------------------------------------------------------------------

export function createSseChat(options: SseChatOptions) {
  const messages = ref<ChatMessage[]>([])
  const streaming = ref(false)
  const error = ref<string | null>(null)

  let abortCtrl: AbortController | null = null

  // Current working assistant message (mutable refs during streaming)
  let currentMsg: ChatMessage | null = null
  let pendingStepMap = new Map<string, number>() // call_id → index in steps[]

  function resetLocal(): void {
    messages.value = []
    streaming.value = false
    error.value = null
    if (abortCtrl) {
      abortCtrl.abort()
      abortCtrl = null
    }
    currentMsg = null
    pendingStepMap.clear()
  }

  function stop(): void {
    if (abortCtrl) {
      abortCtrl.abort()
      abortCtrl = null
    }
    // Finalize current message if any
    if (currentMsg) {
      // Mark all pending steps as done
      for (const step of currentMsg.steps) {
        step.done = true
      }
      currentMsg = null
      pendingStepMap.clear()
    }
    streaming.value = false
  }

  async function send(
    vehicleId: string,
    message: string,
    sessionId: string | null = null,
  ): Promise<void> {
    if (streaming.value) return

    // Push user message
    messages.value.push({ role: 'user', text: message, steps: [] })

    streaming.value = true
    error.value = null

    abortCtrl = new AbortController()

    const url = apiUrl(`/api/chat/${encodeURIComponent(vehicleId)}`)
    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null
    let buffer = ''

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${getAuthToken() ?? ''}`,
          Accept: 'text/event-stream',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message,
          session_id: sessionId,
          language: locale.value,
        }),
        signal: abortCtrl.signal,
      })

      if (!response.ok) {
        // Try to parse error detail as JSON
        let errMsg = `HTTP ${response.status}`
        try {
          const errJson = await response.json()
          if (errJson.detail) errMsg = formatApiDetail(errJson.detail)
        } catch {
          /* keep default */
        }
        error.value = errMsg
        streaming.value = false
        return
      }

      reader = response.body!.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        // Process complete frames from the buffer
        const frames = parseSseFrames(buffer)
        // Keep unprocessed tail in buffer
        const lastDoubleNewline = buffer.lastIndexOf('\n\n')
        if (lastDoubleNewline === -1) {
          buffer = ''
        } else {
          buffer = buffer.slice(lastDoubleNewline + 2)
        }

        for (const frame of frames) {
          await handleSseEvent(frame, vehicleId)
        }
      }
    } catch (e: unknown) {
      if (e instanceof Error && e.name === 'AbortError') {
        // Finalize current message on abort
        if (currentMsg) {
          for (const step of currentMsg.steps) {
            step.done = true
          }
          currentMsg = null
          pendingStepMap.clear()
        }
      } else {
        error.value = e instanceof Error ? e.message : t('chat.error.connection')
      }
    } finally {
      if (reader) {
        try { reader.releaseLock() } catch { /* ignore */ }
      }
      streaming.value = false
      abortCtrl = null
    }
  }

  async function handleSseEvent(
    frame: SseFrame,
    _vehicleId: string,
  ): Promise<void> {
    // Parse JSON data
    let json: Record<string, unknown>
    try {
      json = JSON.parse(frame.data) as Record<string, unknown>
    } catch {
      return // skip malformed frames
    }

    switch (frame.event) {
      case 'token': {
        const text = String(json.text ?? '')
        if (!currentMsg) {
          currentMsg = { role: 'assistant', text: '', steps: [] }
          messages.value.push(currentMsg)
        }
        currentMsg.text += text
        break
      }

      case 'reasoning': {
        // Ignore reasoning (subtle "thinking" — not rendered)
        break
      }

      case 'tool_start': {
        const callId = String(json.call_id ?? '')
        const name = String(json.name ?? '')
        if (!currentMsg) {
          currentMsg = { role: 'assistant', text: '', steps: [] }
          messages.value.push(currentMsg)
        }
        const step: AgentStepT = {
          call_id: callId,
          name,
          summary: null,
          content: null,
          is_error: false,
          done: false,
        }
        currentMsg.steps.push(step)
        pendingStepMap.set(callId, currentMsg.steps.length - 1)
        break
      }

      case 'tool_result': {
        const callId = String(json.call_id ?? '')
        const name = String(json.name ?? '')
        const summary = String(json.summary ?? '')
        const content = String(json.content ?? '')
        const isErr = Boolean(json.is_error)

        // Update or create step
        let stepIdx = pendingStepMap.get(callId)
        if (stepIdx === undefined) {
          if (!currentMsg) {
            currentMsg = { role: 'assistant', text: '', steps: [] }
            messages.value.push(currentMsg)
          }
          const step: AgentStepT = {
            call_id: callId,
            name,
            summary,
            content,
            is_error: isErr,
            done: true,
          }
          currentMsg.steps.push(step)
        } else {
          const step = currentMsg!.steps[stepIdx]
          step.summary = summary
          step.content = content
          step.is_error = isErr
          step.done = true
        }

        // If this is the diagnostic result, set a flag on the message
        if (name === 'get_diagnostic_result' && !isErr) {
          const diag = parseDiagnosticResult(content)
          if (diag) {
            ;(currentMsg as ChatMessage & { _diag?: DiagnosticResult })._diag = diag
          }
        }
        break
      }

      case 'ticket_draft': {
        const draft: TicketDraftEvent = {
          payload: json.payload as unknown as TicketDraftEvent['payload'],
          priority_rationale: String(json.priority_rationale ?? ''),
          urgency_source:
            (json.urgency_source as 'agent' | 'rules') ?? 'agent',
          session_id: String(json.session_id ?? ''),
        }
        options.onTicketDraft(draft)
        break
      }

      case 'document': {
        const docId = String(json.doc_id ?? '')
        const pagePdf = typeof json.page_pdf === 'number' ? json.page_pdf : 1
        options.onDocument(docId, pagePdf)
        break
      }

      case 'turn_done': {
        // Finalize — nothing extra needed
        if (currentMsg) {
          for (const step of currentMsg.steps) {
            step.done = true
          }
          currentMsg = null
          pendingStepMap.clear()
        }
        break
      }

      case 'error': {
        const errMsg = String(json.message ?? 'Ошибка')
        error.value = errMsg
        break
      }

      default: {
        // Unknown event — ignore
        break
      }
    }
  }

  return { messages, streaming, error, resetLocal, send, stop }
}
