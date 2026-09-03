<script setup>
/* "Order court research" modal — opened from the entity sidebar (login-gated).
 * The visitor picks a scope (this company / whole network) and a search type
 * (by EIK / by EIK + name), sees a live price, and places an order. The price is
 * recomputed server-side on submit; what we show here is an estimate from the same
 * constants (frontend/src/lib/researchPricing.js, mirrors backend/app/pricing.py). */
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { companyCount, quote } from '../lib/researchPricing'

const { t } = useI18n()
const props = defineProps({
  ekey: { type: String, required: true },
  profile: { type: Object, required: true },
  nodes: { type: Array, default: () => [] },
  depth: { type: Number, default: 2 },
})
const emit = defineEmits(['close'])

// "This company" only makes sense for a company that has an EIK to search by.
const canCompanyScope = computed(() =>
  props.profile?.kind === 'company' && !!props.profile?.eik)

const scope = ref(canCompanyScope.value ? 'company' : 'network')
const searchType = ref('eik')
const details = ref('')

const networkCompanies = computed(() => companyCount(props.nodes))
const billedCount = computed(() =>
  scope.value === 'network' ? networkCompanies.value : (canCompanyScope.value ? 1 : 0))
const price = computed(() => quote(scope.value, networkCompanies.value, searchType.value))

const busy = ref(false)
const err = ref(null)
const done = ref(false)
const finalPrice = ref(0)

async function submit() {
  busy.value = true
  err.value = null
  const body = { key: props.ekey, scope: scope.value, search_type: searchType.value, depth: props.depth }
  if (details.value.trim()) body.details = details.value.trim()
  try {
    const res = await api.createCourtOrder(body)
    finalPrice.value = res.price_eur
    done.value = true
  } catch {
    err.value = t('courtOrder.errGeneric')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="backdrop">
    <div class="modal">
      <button class="x" @click="emit('close')" :aria-label="$t('common.close')">✕</button>

      <template v-if="!done">
        <h2 class="display title">{{ $t('courtOrder.title') }}</h2>
        <p class="sub">{{ $t('courtOrder.sub') }}</p>

        <form @submit.prevent="submit">
          <div class="group">
            <span class="lbl">{{ $t('courtOrder.scopeLabel') }}</span>
            <label v-if="canCompanyScope" class="opt" :class="{ on: scope === 'company' }">
              <input type="radio" value="company" v-model="scope" />
              <span>{{ $t('courtOrder.scopeCompany') }}</span>
            </label>
            <label class="opt" :class="{ on: scope === 'network' }">
              <input type="radio" value="network" v-model="scope" />
              <span>{{ $t('courtOrder.scopeNetwork', { count: networkCompanies }) }}</span>
            </label>
          </div>

          <div class="group">
            <span class="lbl">{{ $t('courtOrder.typeLabel') }}</span>
            <label class="opt" :class="{ on: searchType === 'eik' }">
              <input type="radio" value="eik" v-model="searchType" />
              <span>{{ $t('courtOrder.typeEik') }}</span>
            </label>
            <label class="opt" :class="{ on: searchType === 'eik_name' }">
              <input type="radio" value="eik_name" v-model="searchType" />
              <span>{{ $t('courtOrder.typeEikName') }}</span>
            </label>
            <p class="hint">{{ $t('courtOrder.typeHint') }}</p>
          </div>

          <label class="field">
            <span class="lbl">{{ $t('courtOrder.notes') }}</span>
            <textarea v-model="details" rows="2" maxlength="2000"
                      :placeholder="$t('courtOrder.notesPlaceholder')"></textarea>
          </label>

          <div class="quote">
            <div class="qline">
              <span>{{ $t('courtOrder.lineCourt') }}<template v-if="scope === 'network'"> · {{ billedCount }}×</template></span>
              <span class="mono">€{{ price.toFixed(2) }}</span>
            </div>
            <div class="qline total">
              <span>{{ $t('courtOrder.total') }}</span>
              <span class="mono">€{{ price.toFixed(2) }}</span>
            </div>
          </div>

          <p v-if="err" class="err">{{ err }}</p>

          <button class="submit" type="submit" :disabled="busy">
            {{ busy ? $t('courtOrder.sending') : $t('courtOrder.submit', { price: price.toFixed(2) }) }}
          </button>
        </form>
      </template>

      <div v-else class="success">
        <h2 class="display title">{{ $t('courtOrder.thanks') }}</h2>
        <p class="sub">{{ $t('courtOrder.thanksSub', { price: Number(finalPrice).toFixed(2) }) }}</p>
        <button class="submit" @click="emit('close')">{{ $t('courtOrder.close') }}</button>
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

.group { margin-bottom: 16px; }
.lbl { display: block; font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; color: #777; margin-bottom: 6px; }
.opt {
  display: flex; align-items: center; gap: 9px; cursor: pointer;
  border: var(--stroke); background: var(--surface); padding: 9px 11px; margin-bottom: 6px;
  font-size: 14px; font-weight: 600;
}
.opt.on { box-shadow: 0 0 0 3px var(--pink); }
.opt input { accent-color: var(--pink); }
.hint { font-size: 11px; color: #777; margin: 4px 0 0; line-height: 1.4; }

.field { display: block; margin-bottom: 16px; }
.field textarea {
  width: 100%; box-sizing: border-box; border: var(--stroke); background: var(--surface);
  padding: 10px 11px; font-size: 14px; font-family: var(--font-mono); resize: vertical;
}
.field textarea:focus { outline: none; box-shadow: 0 0 0 3px var(--pink); }

.quote { border: var(--stroke); background: #FFF8EC; padding: 10px 12px; margin-bottom: 14px; }
.qline { display: flex; justify-content: space-between; font-size: 13px; padding: 2px 0; }
.qline.total { font-weight: 800; font-family: var(--font-display); font-size: 16px; border-top: var(--stroke); margin-top: 6px; padding-top: 8px; }

.err { color: var(--pink); font-size: 12px; font-weight: 700; margin: 4px 0 12px; }

.submit {
  width: 100%; border: var(--stroke); background: var(--pink); color: #fff;
  box-shadow: var(--shadow); padding: 12px; font-weight: 800; font-family: var(--font-display);
  text-transform: uppercase; cursor: pointer; margin-top: 4px;
}
.submit:active { transform: translate(2px, 2px); box-shadow: 2px 2px 0 0 var(--ink); }
.submit:disabled { opacity: 0.6; cursor: default; }

.success { text-align: center; padding: 8px 0; }
.success .sub { margin-bottom: 18px; }

@media (max-width: 768px) {
  .backdrop { align-items: flex-start; overflow-y: auto; padding: max(7vh, 20px) 14px 20px; }
  .modal { padding: 22px 18px; }
  .field textarea { font-size: 16px; }
}
</style>
