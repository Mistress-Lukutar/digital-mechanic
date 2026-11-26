import { ref } from 'vue'
import ru from './locales/ru'

export type Locale = 'ru' | 'kk' | 'uz' | 'hi'

export type Messages = typeof ru
export type MessageKey = keyof Messages

// ---------------------------------------------------------------------------
// Singleton locale state
// ---------------------------------------------------------------------------

export const locale = ref<Locale>('ru')

// ---------------------------------------------------------------------------
// Dictionaries — kk/uz/hi will be added later; t() falls back to ru.
// ---------------------------------------------------------------------------

const dictionaries: Partial<Record<Locale, Messages>> = { ru }

// ---------------------------------------------------------------------------
// Translation lookup with placeholder replacement
// ---------------------------------------------------------------------------

export function t(
  key: MessageKey,
  params?: Record<string, string | number>,
): string {
  const dict = dictionaries[locale.value] ?? ru
  const raw = dict[key]

  if (raw === undefined || raw === null) {
    console.warn(`[i18n] Missing key: ${String(key)}`)
    return String(key)
  }

  // Replace {name} placeholders from params
  if (params) {
    let result = raw
    for (const [name, value] of Object.entries(params)) {
      result = result.replace(new RegExp(`\\{${name}\\}`, 'g'), String(value))
    }
    return result
  }

  return raw
}

// ---------------------------------------------------------------------------
// Locale switching
// ---------------------------------------------------------------------------

export function setLocale(l: Locale): void {
  locale.value = l
  localStorage.setItem('dm_locale', l)
  document.documentElement.lang = l
}

const KNOWN_LOCALES: ReadonlySet<Locale> = new Set(['ru', 'kk', 'uz', 'hi'])

export function initLocale(): void {
  const stored = localStorage.getItem('dm_locale')
  if (stored && KNOWN_LOCALES.has(stored as Locale)) {
    locale.value = stored as Locale
  } else {
    locale.value = 'ru'
  }
  document.documentElement.lang = locale.value
}

// ---------------------------------------------------------------------------
// Locale options for the switcher component
// ---------------------------------------------------------------------------

export const LOCALE_OPTIONS: ReadonlyArray<{ value: Locale; native: string }> = [
  { value: 'ru', native: 'Русский' },
  { value: 'kk', native: 'Қазақша' },
  { value: 'uz', native: "Oʻzbekcha" },
  { value: 'hi', native: 'हिन्दी' },
]
