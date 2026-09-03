<script setup>
/* Login / Register modal. Email+password posts to fastapi-users; "Continue with
 * Google" redirects to the backend OAuth flow. Opened via authStore.openModal(). */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/authStore'
import { navigate } from '../router'

const { t } = useI18n()
const auth = useAuthStore()
// Flip to true once a Google OAuth client is configured on the server.
const GOOGLE_ENABLED = false
const mode = ref('login') // 'login' | 'register'
const email = ref('')
const password = ref('')
const name = ref('')
const agreed = ref(false) // register-only: must accept Terms & Privacy
const busy = ref(false)
const err = ref(null)

function setMode(m) { mode.value = m; err.value = null }

function gotoLegal(path) { auth.closeModal(); navigate(path) }

async function submit() {
  if (mode.value === 'register' && !agreed.value) {
    err.value = t('auth.acceptTerms')
    return
  }
  busy.value = true
  err.value = null
  try {
    if (mode.value === 'login') await auth.login(email.value, password.value)
    else await auth.register(email.value, password.value, name.value)
    auth.closeModal()
  } catch (e) {
    err.value = mode.value === 'login'
      ? t('auth.wrongCredentials')
      : String(e.message || e)
  } finally {
    busy.value = false
  }
}

async function google() {
  busy.value = true
  try { await auth.startGoogle() } catch (e) { err.value = String(e.message || e); busy.value = false }
}
</script>

<template>
  <div class="backdrop" @click.self="auth.closeModal()">
    <div class="modal">
      <button class="x" @click="auth.closeModal()" :aria-label="$t('common.close')">✕</button>

      <h2 class="display title">{{ mode === 'login' ? $t('auth.signIn') : $t('auth.createAccount') }}</h2>
      <p class="sub">{{ $t('auth.sub') }}</p>

      <div class="seg">
        <button :class="{ on: mode === 'login' }" @click="setMode('login')">{{ $t('auth.signIn') }}</button>
        <button :class="{ on: mode === 'register' }" @click="setMode('register')">{{ $t('auth.register') }}</button>
      </div>

      <template v-if="GOOGLE_ENABLED">
        <button class="google" :disabled="busy" @click="google">
          <span class="g">G</span> {{ $t('auth.continueGoogle') }}
        </button>
        <div class="or"><span>{{ $t('auth.or') }}</span></div>
      </template>

      <form @submit.prevent="submit">
        <label v-if="mode === 'register'" class="field">
          <span class="lbl">{{ $t('auth.name') }}</span>
          <input v-model="name" type="text" autocomplete="name" />
        </label>
        <label class="field">
          <span class="lbl">{{ $t('auth.email') }}</span>
          <input v-model="email" type="email" autocomplete="email" required />
        </label>
        <label class="field">
          <span class="lbl">{{ $t('auth.password') }}</span>
          <input v-model="password" type="password" autocomplete="current-password"
                 minlength="8" required />
        </label>

        <label v-if="mode === 'register'" class="consent">
          <input v-model="agreed" type="checkbox" />
          <span>
            {{ $t('auth.agreePre') }}
            <a href="/terms" @click.prevent="gotoLegal('/terms')">{{ $t('auth.terms') }}</a>
            {{ $t('auth.agreeMid') }}
            <a href="/privacy" @click.prevent="gotoLegal('/privacy')">{{ $t('auth.privacy') }}</a>.
          </span>
        </label>

        <p v-if="err" class="err">{{ err }}</p>

        <button class="submit" type="submit" :disabled="busy">
          {{ busy ? '…' : (mode === 'login' ? $t('auth.signIn') : $t('auth.createAccount')) }}
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(13, 13, 13, 0.45);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.modal {
  position: relative; width: 100%; max-width: 380px;
  background: var(--surface); border: var(--stroke-thick); box-shadow: var(--shadow-lg);
  padding: 26px 24px;
}
.x {
  position: absolute; top: 10px; right: 10px;
  border: var(--stroke); background: var(--surface); width: 28px; height: 28px;
  font-weight: 800; cursor: pointer; box-shadow: var(--shadow);
}
.title { font-size: 28px; line-height: 1; }
.sub { margin: 6px 0 18px; font-size: 13px; color: #555; }

.seg { display: flex; border: var(--stroke); box-shadow: var(--shadow); margin-bottom: 18px; }
.seg button {
  flex: 1; border: none; border-right: var(--stroke); background: var(--surface);
  padding: 9px 0; font-weight: 800; font-family: var(--font-display); cursor: pointer;
}
.seg button:last-child { border-right: none; }
.seg button.on { background: var(--pink); color: #fff; }

.google {
  width: 100%; border: var(--stroke); background: var(--surface); box-shadow: var(--shadow);
  padding: 11px; font-weight: 700; cursor: pointer; display: flex; align-items: center;
  justify-content: center; gap: 10px;
}
.google:active { transform: translate(2px, 2px); box-shadow: 2px 2px 0 0 var(--ink); }
.google .g {
  font-family: var(--font-display); font-weight: 800; background: var(--ink); color: #fff;
  width: 20px; height: 20px; display: inline-flex; align-items: center; justify-content: center;
}

.or { display: flex; align-items: center; gap: 10px; margin: 16px 0; color: #999; font-size: 12px; }
.or::before, .or::after { content: ''; flex: 1; height: 2px; background: var(--neutral); }

.field { display: block; margin-bottom: 12px; }
.lbl { display: block; font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; color: #777; margin-bottom: 4px; }
.field input {
  width: 100%; box-sizing: border-box; border: var(--stroke); background: var(--surface);
  padding: 10px 11px; font-size: 14px; font-family: var(--font-mono);
}
.field input:focus { outline: none; box-shadow: 0 0 0 3px var(--pink); }

.consent { display: flex; gap: 8px; align-items: flex-start; margin: 2px 0 12px; font-size: 12px; line-height: 1.45; color: #444; }
.consent input { margin-top: 2px; flex: none; width: 15px; height: 15px; accent-color: var(--pink); }
.consent a { color: var(--pink); font-weight: 700; }

.err { color: var(--pink); font-size: 12px; font-weight: 700; margin: 4px 0 12px; }

.submit {
  width: 100%; border: var(--stroke); background: var(--pink); color: #fff;
  box-shadow: var(--shadow); padding: 12px; font-weight: 800; font-family: var(--font-display);
  text-transform: uppercase; cursor: pointer; margin-top: 4px;
}
.submit:active { transform: translate(2px, 2px); box-shadow: 2px 2px 0 0 var(--ink); }
.submit:disabled { opacity: 0.6; cursor: default; }

/* Mobile: top-align and let the backdrop scroll so the on-screen keyboard
   doesn't hide the form. 16px inputs prevent the iOS focus auto-zoom. */
@media (max-width: 768px) {
  .backdrop {
    align-items: flex-start;
    overflow-y: auto;
    padding: max(7vh, 20px) 14px 20px;
  }
  .modal { padding: 22px 18px; }
  .field input { font-size: 16px; }
}
</style>
