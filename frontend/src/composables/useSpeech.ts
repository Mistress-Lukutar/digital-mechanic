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

  function start(onFinalText: (text: string) => void): void {
    // Guard: already listening
    if (listening.value) return

    const ctor = getRecognitionCtor()
    if (!ctor) return

    recognition = new ctor()!
    recognition.lang = LANG_MAP[locale.value]
    recognition.continuous = false
    recognition.interimResults = true

    let finalTranscript = ''

    recognition.onresult = (e: any) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const result = e.results[i]
        if (result.isFinal) {
          finalTranscript += result[0].transcript
        }
      }
      // When the last result is final, send it and stop.
      if (e.results[e.results.length - 1].isFinal) {
        const text = finalTranscript.trim()
        if (text) onFinalText(text)
        recognition?.stop()
      }
    }

    recognition.onerror = (_e: any) => {
      console.warn('[useSpeech] recognition error:', _e.error ?? _e.message)
      listening.value = false
      clearSafetyTimer()
    }

    recognition.onend = () => {
      listening.value = false
      recognition = null
      clearSafetyTimer()
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

  function stop(): void {
    if (recognition) {
      try { recognition.stop() } catch { /* ignore */ }
      recognition = null
    }
    clearSafetyTimer()
  }

  return { supported, listening, start, stop }
}
