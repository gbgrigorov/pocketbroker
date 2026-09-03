// i18n bootstrap. UI chrome is translatable (EN/BG); all DB-sourced data
// (names, statuses, legal forms, roles, addresses, property-type keys) stays in
// its original Cyrillic and is NEVER routed through the message catalog.
//
// Default locale is Bulgarian; the choice persists in localStorage and is
// mirrored onto <html lang> for accessibility/SEO.
import { createI18n } from 'vue-i18n'
import en from './messages/en'
import bg from './messages/bg'

export const SUPPORTED = ['bg', 'en']
const STORAGE_KEY = 'locale'

function initialLocale() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && SUPPORTED.includes(saved)) return saved
  } catch { /* localStorage unavailable — fall through to default */ }
  return 'bg'
}

const i18n = createI18n({
  legacy: false,          // Composition API mode
  globalInjection: true,  // expose $t in every template without per-component imports
  locale: initialLocale(),
  fallbackLocale: 'en',
  messages: { en, bg },
})

document.documentElement.lang = i18n.global.locale.value

// Switch the active UI language and remember it.
export function setLocale(locale) {
  if (!SUPPORTED.includes(locale)) return
  i18n.global.locale.value = locale
  try { localStorage.setItem(STORAGE_KEY, locale) } catch { /* ignore */ }
  document.documentElement.lang = locale
}

export function currentLocale() {
  return i18n.global.locale.value
}

export default i18n
