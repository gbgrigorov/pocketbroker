<script setup>
/* "Order a research" modal — shown from the empty state of the Builders & Companies
 * search. The visitor tells us which company to research and how to reach them; we
 * store it for manual follow-up. A server-verified math CAPTCHA + a hidden honeypot
 * keep bots out (the answer is checked on the backend — see app/captcha.py). */
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { quoteSingle } from '../lib/researchPricing'

const { t } = useI18n()
const props = defineProps({
  initialCompany: { type: String, default: '' },
  initialQuery: { type: String, default: '' },
})
const emit = defineEmits(['close'])

const company = ref(props.initialCompany)
const eik = ref('')
const owner = ref('')
const details = ref('')
const name = ref('')
const email = ref('')
const answer = ref('')
const website = ref('') // honeypot — must stay empty

const challenge = ref(null) // { question, exp, sig }
const busy = ref(false)
const err = ref(null)
const done = ref(false)
const step = ref('form') // 'form' (details) → 'expedite' (queue vs rush)
const wasExpedited = ref(false)
const quotedPrice = ref(0)

// Expedite price for the one requested company: by EIK (€1) when we have an EIK,
// otherwise name-only (the fuzzier 3× tier). Server recomputes this authoritatively.
const expediteSearchType = computed(() => (eik.value.trim() ? 'eik' : 'eik_name'))
const expeditePrice = computed(() => quoteSingle(expediteSearchType.value))

async function loadChallenge() {
  try {
    challenge.value = await api.researchChallenge()
  } catch {
    challenge.value = null
  }
  answer.value = ''
}

onMounted(loadChallenge)

// Step 1 → step 2. Native form validation has already passed (required fields).
function toExpedite() {
  err.value = null
  step.value = 'expedite'
}

async function submit(expedited) {
  if (!challenge.value) { err.value = t('research.errLoad'); step.value = 'form'; return }
  busy.value = true
  err.value = null
  // Only send fields that have a value; the backend forbids unknown/empty-malformed input.
  const body = {
    company_name: company.value,
    requester_email: email.value,
    captcha_answer: Number(answer.value),
    captcha_exp: challenge.value.exp,
    captcha_sig: challenge.value.sig,
    website: website.value,
  }
  if (eik.value.trim()) body.company_eik = eik.value.trim()
  if (owner.value.trim()) body.owner = owner.value.trim()
  if (details.value.trim()) body.details = details.value.trim()
  if (name.value.trim()) body.requester_name = name.value.trim()
  if (props.initialQuery.trim()) body.search_query = props.initialQuery.trim()
  if (expedited) { body.expedited = true; body.search_type = expediteSearchType.value }

  try {
    const res = await api.createResearchRequest(body)
    wasExpedited.value = expedited
    quotedPrice.value = res.price_eur || 0
    done.value = true
  } catch (e) {
    if (String(e.message) === 'captcha') {
      err.value = t('research.errCaptcha')
      step.value = 'form'
      await loadChallenge() // the old challenge is spent/expired
    } else {
      err.value = t('research.errGeneric')
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="backdrop">
    <div class="modal">
      <button class="x" @click="emit('close')" :aria-label="$t('common.close')">✕</button>

      <template v-if="!done && step === 'form'">
        <h2 class="display title">{{ $t('research.title') }}</h2>
        <p class="sub">{{ $t('research.sub') }}</p>

        <form @submit.prevent="toExpedite">
          <label class="field">
            <span class="lbl">{{ $t('research.company') }}</span>
            <input v-model="company" type="text" maxlength="200" required />
          </label>
          <div class="row2">
            <label class="field">
              <span class="lbl">{{ $t('research.eik') }}</span>
              <input v-model="eik" type="text" inputmode="numeric" maxlength="13" :placeholder="$t('research.eikPlaceholder')" />
            </label>
            <label class="field">
              <span class="lbl">{{ $t('research.owner') }}</span>
              <input v-model="owner" type="text" maxlength="200" />
            </label>
          </div>
          <label class="field">
            <span class="lbl">{{ $t('research.details') }}</span>
            <textarea v-model="details" rows="3" maxlength="2000"
                      :placeholder="$t('research.detailsPlaceholder')"></textarea>
          </label>

          <div class="row2">
            <label class="field">
              <span class="lbl">{{ $t('research.name') }}</span>
              <input v-model="name" type="text" maxlength="120" autocomplete="name" />
            </label>
            <label class="field">
              <span class="lbl">{{ $t('research.email') }}</span>
              <input v-model="email" type="email" autocomplete="email" required />
            </label>
          </div>

          <!-- honeypot: off-screen, never shown to real users -->
          <div class="hp" aria-hidden="true">
            <label>{{ $t('research.website') }}<input v-model="website" type="text" tabindex="-1" autocomplete="off" /></label>
          </div>

          <label class="field captcha">
            <span class="lbl">{{ $t('research.captcha', { q: challenge ? challenge.question : '…' }) }}</span>
            <input v-model="answer" type="number" inputmode="numeric" required :disabled="!challenge" />
          </label>

          <p v-if="err" class="err">{{ err }}</p>

          <button class="submit" type="submit" :disabled="busy || !challenge">
            {{ $t('research.continue') }}
          </button>
        </form>
      </template>

      <template v-else-if="!done && step === 'expedite'">
        <h2 class="display title">{{ $t('research.title') }}</h2>
        <p class="sub">{{ $t('research.expedite.indexPace') }}</p>

        <button class="choice" :disabled="busy" @click="submit(false)">
          <span class="choice-h">{{ $t('research.expedite.queueTitle') }}</span>
          <span class="choice-d">{{ $t('research.expedite.queueDesc') }}</span>
        </button>
        <button class="choice rush" :disabled="busy" @click="submit(true)">
          <span class="choice-h">{{ $t('research.expedite.rushBtn', { price: expeditePrice.toFixed(2) }) }}</span>
          <span class="choice-d">{{ $t('research.expedite.rushDesc', { price: expeditePrice.toFixed(2) }) }}</span>
        </button>

        <p v-if="err" class="err">{{ err }}</p>
        <button class="link-back" :disabled="busy" @click="step = 'form'">{{ $t('research.expedite.back') }}</button>
      </template>

      <div v-else class="success">
        <h2 class="display title">{{ $t('research.thanks') }}</h2>
        <p class="sub">{{ wasExpedited ? $t('research.expedite.thanksRush', { price: Number(quotedPrice).toFixed(2) }) : $t('research.expedite.thanksQueued') }}</p>
        <button class="submit" @click="emit('close')">{{ $t('research.close') }}</button>
      </div>
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
  position: relative; width: 100%; max-width: 460px;
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

.row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

.field { display: block; margin-bottom: 12px; }
.lbl { display: block; font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; color: #777; margin-bottom: 4px; }
.field input, .field textarea {
  width: 100%; box-sizing: border-box; border: var(--stroke); background: var(--surface);
  padding: 10px 11px; font-size: 14px; font-family: var(--font-mono);
}
.field textarea { resize: vertical; }
.field input:focus, .field textarea:focus { outline: none; box-shadow: 0 0 0 3px var(--pink); }
.captcha input { max-width: 120px; }

/* honeypot: keep it in the DOM + focusable for bots, invisible to humans */
.hp { position: absolute; left: -9999px; width: 1px; height: 1px; overflow: hidden; }

.err { color: var(--pink); font-size: 12px; font-weight: 700; margin: 4px 0 12px; }

.submit {
  width: 100%; border: var(--stroke); background: var(--pink); color: #fff;
  box-shadow: var(--shadow); padding: 12px; font-weight: 800; font-family: var(--font-display);
  text-transform: uppercase; cursor: pointer; margin-top: 4px;
}
.submit:active { transform: translate(2px, 2px); box-shadow: 2px 2px 0 0 var(--ink); }
.submit:disabled { opacity: 0.6; cursor: default; }

/* expedite step: two stacked choice cards */
.choice {
  display: block; width: 100%; text-align: left; cursor: pointer;
  border: var(--stroke); background: var(--surface); box-shadow: var(--shadow);
  padding: 12px 14px; margin-bottom: 12px;
}
.choice:active { transform: translate(2px, 2px); box-shadow: 2px 2px 0 0 var(--ink); }
.choice:disabled { opacity: 0.6; cursor: default; }
.choice.rush { background: var(--pink); color: #fff; }
.choice-h { display: block; font-weight: 800; font-family: var(--font-display); text-transform: uppercase; font-size: 15px; }
.choice-d { display: block; font-size: 12px; margin-top: 3px; opacity: 0.85; }
.link-back {
  border: none; background: none; cursor: pointer; color: #555;
  font-size: 12px; text-decoration: underline; padding: 4px 0; margin-top: 2px;
}

.success { text-align: center; padding: 8px 0; }
.success .sub { margin-bottom: 18px; }

/* Mobile: top-align + scrollable backdrop so the keyboard doesn't hide fields;
   16px inputs prevent the iOS focus auto-zoom. */
@media (max-width: 768px) {
  .backdrop { align-items: flex-start; overflow-y: auto; padding: max(7vh, 20px) 14px 20px; }
  .modal { padding: 22px 18px; }
  .row2 { grid-template-columns: 1fr; gap: 0; }
  .field input, .field textarea { font-size: 16px; }
}
</style>
