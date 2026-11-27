import { ref, computed } from 'vue'
import { locale } from '../i18n'
import type { Locale } from '../i18n'

// ---------------------------------------------------------------------------
// Minimal local typing for the Web Speech API (no DOM lib dependency).
// ---------------------------------------------------------------------------

interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  start(): void
  stop(): void
  onresult: ((e: any) => void) | null
  onerror: ((e: any) => void) | null
  onend: (() => void) | null
}

const LANG_MAP: Record<Locale, string> = {
  ru: 'ru-RU',
  kk: 'kk-KZ',
  uz: 'uz-UZ',
  hi: 'hi-IN',
}

function getRecognitionCtor(): new () => SpeechRecognitionLike | null {
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognitionLike
    webkitSpeechRecognition?: new () => SpeechRecognitionLike
  }
  return (
    (w.SpeechRecognition as new () => SpeechRecognitionLike) ??
    (w.webkitSpeechRecognition as new () => SpeechRecognitionLike) ??
    (null as unknown as new () => SpeechRecognitionLike)
  )
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useSpeech() {
  const listening = ref(false)
  const errorCode = ref<string | null>(null)
  const _ctor = getRecognitionCtor()
  const supported = computed(() => _ctor !== null)

  let recognition: SpeechRecognitionLike | null = null
  let safetyTimer: ReturnType<typeof setTimeout> | null = null

  function clearSafetyTimer(): void {
    if (safetyTimer !== null) {
      clearTimeout(safetyTimer)
      safetyTimer = null
    }
  }

  // Session-scoped state (shared across start/stop/onresult/onend)
  let lastFinalText = ''
  let sentThisSession = false
  let sendOnEnd = false
  let finalCallback: ((text: string) => void) | null = null

  function deliverFinalText(): void {
    const text = lastFinalText.trim()
    if (text && finalCallback) {
      finalCallback(text)
    }
  }

  function start(onFinalText: (text: string) => void): void {
    // Guard: already listening
    if (listening.value) return

    errorCode.value = null

    // Secure-context guard (Safari/iOS requires HTTPS for SpeechRecognition)
    if (!window.isSecureContext) {
      errorCode.value = 'insecure'
      return
    }

    const ctor = getRecognitionCtor()
    if (!ctor) return

    // Reset session state
    lastFinalText = ''
    sentThisSession = false
    sendOnEnd = false
    finalCallback = onFinalText

    recognition = new ctor()!
    recognition.lang = LANG_MAP[locale.value]
    recognition.continuous = false
    recognition.interimResults = true

    recognition.onresult = (e: any) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const result = e.results[i]
        if (result.isFinal) {
          lastFinalText += result[0].transcript
        }
      }
      // When the last result is final, send it once and stop.
      if (e.results[e.results.length - 1].isFinal && !sentThisSession) {
        sentThisSession = true
        deliverFinalText()
        recognition?.stop()
      }
    }

    recognition.onerror = (e: any) => {
      const code = String(e?.error ?? '')
      if (code === 'not-allowed' || code === 'service-not-allowed') errorCode.value = 'denied'
      else if (code === 'network') errorCode.value = 'network'
      else if (code === 'audio-capture') errorCode.value = 'no-mic'
      else if (code === 'language-not-supported') errorCode.value = 'lang'
      else if (code === 'no-speech') errorCode.value = 'no-speech'
      else errorCode.value = 'generic'
      listening.value = false
      clearSafetyTimer()
    }

    recognition.onend = () => {
      listening.value = false
      recognition = null
      clearSafetyTimer()
      if (sendOnEnd && !sentThisSession) {
        sentThisSession = true
        deliverFinalText()
      }
    }

    listening.value = true

    // Auto-stop safety: 15 s hard limit
    safetyTimer = setTimeout(() => {
      if (listening.value) {
        recognition?.stop()
      }
    }, 15_000)

    try {
      recognition.start()
    } catch {
      // Mic denied or other start failure
      listening.value = false
      recognition = null
      clearSafetyTimer()
    }
  }

  function stop(sendText = false): void {
    if (sendText) sendOnEnd = true
    if (recognition) {
      try { recognition.stop() } catch { /* ignore */ }
      recognition = null
    } else if (sendText && !sentThisSession) {
      // Recognition already ended — deliver whatever was recognized.
      sentThisSession = true
      deliverFinalText()
    }
    clearSafetyTimer()
  }

  return { supported, listening, error: errorCode, start, stop }
}
