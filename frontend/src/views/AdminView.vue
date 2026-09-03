<script setup>
/* Semi-admin page (superuser only): two read-only tables — every research request
 * (leads + court orders + expedite) and every registered user. The real gate is the
 * API (current_superuser → 401/403); this view also guards client-side so a non-admin
 * who navigates to /admin sees a notice instead of empty tables. */
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { useAuthStore } from '../stores/authStore'
import { setPageMeta } from '../lib/pageMeta'

const auth = useAuthStore()
const { t } = useI18n()
const authReady = computed(() => auth.ready)
const isAdmin = computed(() => !!auth.user?.is_superuser)

const tab = ref('requests') // 'requests' | 'users'
const requests = ref([])
const users = ref([])
const loading = ref(true)
const error = ref(false)

function fmtDate(s) {
  if (!s) return '—'
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? s : d.toLocaleString('bg-BG', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}
function fmtPrice(v) {
  return v == null ? '—' : '€' + Number(v).toFixed(2)
}
function fmtDay(s) {
  if (!s) return '—'
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? s : d.toLocaleDateString('bg-BG', {
    year: 'numeric', month: '2-digit', day: '2-digit',
  })
}
// Tooltips spell out what an unticked box means — "not checked" is not "clean".
function networkTitle(r) {
  if (!r.company_eik) return t('admin.req.networkNoEik')
  return r.in_db
    ? t('admin.req.networkYes', { n: r.edge_count })
    : t('admin.req.networkNo')
}
function courtTitle(r) {
  if (!r.court_checked_at) return t('admin.req.courtNever')
  return t('admin.req.courtYes', { d: fmtDay(r.court_checked_at), n: r.court_acts ?? 0 })
}
function scopeText(r) {
  if (r.order_type !== 'court_research') return '—'
  const bits = [r.scope, r.search_type].filter(Boolean)
  return bits.join(' · ') || '—'
}

async function load() {
  if (!authReady.value) return // still resolving — the watcher re-fires when it lands
  if (!isAdmin.value) { loading.value = false; return }
  loading.value = true
  error.value = false
  try {
    const [rq, us] = await Promise.all([api.adminResearchRequests(), api.adminUsers()])
    requests.value = rq
    users.value = us
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

// On a hard refresh App.vue fires fetchMe() without awaiting it, so this view can
// mount before the session is known. Waiting on `ready` (rather than firing once on
// mount) is what makes Ctrl-R land on the data instead of an empty table.
watch(authReady, (ok) => { if (ok) load() }, { immediate: true })

onMounted(() => {
  setPageMeta({ title: 'Admin — BG INTEL', description: '' })
})
</script>

<template>
  <div class="admin">
    <header class="head">
      <h1 class="display title">{{ $t('admin.title') }}</h1>
      <div v-if="isAdmin" class="seg">
        <button :class="{ on: tab === 'requests' }" @click="tab = 'requests'">
          {{ $t('admin.tabRequests', { n: requests.length }) }}
        </button>
        <button :class="{ on: tab === 'users' }" @click="tab = 'users'">
          {{ $t('admin.tabUsers', { n: users.length }) }}
        </button>
      </div>
    </header>

    <!-- Order matters: "not authorized" must not flash while the session is still
         resolving, so an unsettled auth state reads as loading, not as denied. -->
    <div v-if="!authReady || loading" class="note">{{ $t('admin.loading') }}</div>
    <div v-else-if="!isAdmin" class="note">{{ $t('admin.notAuthorized') }}</div>
    <div v-else-if="error" class="note err">{{ $t('admin.error') }}</div>

    <template v-else>
      <!-- Requests -->
      <div v-if="tab === 'requests'" class="tablewrap">
        <div v-if="!requests.length" class="note">{{ $t('admin.empty') }}</div>
        <table v-else class="tbl">
          <thead>
            <tr>
              <th>{{ $t('admin.req.date') }}</th>
              <th>{{ $t('admin.req.type') }}</th>
              <th>{{ $t('admin.req.company') }}</th>
              <th>{{ $t('admin.req.scope') }}</th>
              <th class="num">{{ $t('admin.req.count') }}</th>
              <th class="num">{{ $t('admin.req.price') }}</th>
              <th class="ctr">{{ $t('admin.req.network') }}</th>
              <th class="ctr">{{ $t('admin.req.court') }}</th>
              <th>{{ $t('admin.req.status') }}</th>
              <th>{{ $t('admin.req.requester') }}</th>
              <th>{{ $t('admin.req.details') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in requests" :key="r.id">
              <td class="mono nowrap">{{ fmtDate(r.created_at) }}</td>
              <td>
                <span class="tag" :class="r.order_type === 'court_research' ? 'court' : 'lead'">
                  {{ r.order_type === 'court_research' ? $t('admin.req.typeCourt') : $t('admin.req.typeLead') }}
                </span>
                <span v-if="r.expedited" class="tag rush">{{ $t('admin.req.expedite') }}</span>
              </td>
              <td>
                <div class="strong">{{ r.company_name }}</div>
                <div v-if="r.company_eik" class="mono dim">{{ r.company_eik }}</div>
              </td>
              <td class="mono dim">{{ scopeText(r) }}</td>
              <td class="num mono">{{ r.entity_count ?? '—' }}</td>
              <td class="num mono">{{ fmtPrice(r.price_eur) }}</td>
              <td class="ctr">
                <span class="box" :class="{ on: r.in_db }" :title="networkTitle(r)">
                  <span v-if="r.in_db" class="tick">✔</span>
                </span>
                <div v-if="r.in_db" class="mono dim tiny">{{ $t('admin.req.edges', { n: r.edge_count }) }}</div>
              </td>
              <td class="ctr">
                <span class="box" :class="{ on: !!r.court_checked_at }" :title="courtTitle(r)">
                  <span v-if="r.court_checked_at" class="tick">✔</span>
                </span>
                <div v-if="r.court_checked_at" class="mono dim tiny">
                  {{ fmtDay(r.court_checked_at) }}<br>{{ $t('admin.req.acts', { n: r.court_acts ?? 0 }) }}
                </div>
              </td>
              <td><span class="tag status">{{ r.status }}</span></td>
              <td>
                <div v-if="r.requester_name">{{ r.requester_name }}</div>
                <a v-if="r.requester_email" :href="`mailto:${r.requester_email}`" class="mono dim link">{{ r.requester_email }}</a>
              </td>
              <td class="details">{{ r.details || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Users -->
      <div v-else class="tablewrap">
        <div v-if="!users.length" class="note">{{ $t('admin.empty') }}</div>
        <table v-else class="tbl">
          <thead>
            <tr>
              <th class="num">{{ $t('admin.usr.id') }}</th>
              <th>{{ $t('admin.usr.email') }}</th>
              <th>{{ $t('admin.usr.name') }}</th>
              <th>{{ $t('admin.usr.tier') }}</th>
              <th>{{ $t('admin.usr.active') }}</th>
              <th>{{ $t('admin.usr.admin') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td class="num mono">{{ u.id }}</td>
              <td class="mono">{{ u.email }}</td>
              <td>{{ u.name || '—' }}</td>
              <td><span class="tag">{{ u.tier }}</span></td>
              <td>{{ u.is_active ? '✓' : '—' }}</td>
              <td>{{ u.is_superuser ? '✓' : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.admin { padding: 24px; max-width: 100%; }
.head { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; margin-bottom: 18px; }
.title { font-size: 34px; line-height: 0.95; }

.seg { display: inline-flex; border: var(--stroke); box-shadow: var(--shadow); }
.seg button {
  border: none; border-right: var(--stroke); background: var(--surface);
  padding: 8px 16px; font-weight: 800; font-family: var(--font-display); cursor: pointer;
}
.seg button:last-child { border-right: none; }
.seg button.on { background: var(--pink); color: #fff; }

.note { padding: 18px; border: var(--stroke); background: var(--surface); box-shadow: var(--shadow); font-size: 14px; }
.note.err { background: var(--pink); color: #fff; }

.tablewrap { overflow-x: auto; border: var(--stroke); box-shadow: var(--shadow-lg); background: var(--surface); }
.tbl { border-collapse: collapse; width: 100%; font-size: 13px; }
.tbl th, .tbl td {
  text-align: left; padding: 9px 12px; border-bottom: var(--stroke); vertical-align: top;
  white-space: normal;
}
.tbl thead th {
  position: sticky; top: 0; background: var(--ink); color: var(--bg);
  font-family: var(--font-display); text-transform: uppercase; font-size: 11px; letter-spacing: 0.04em;
}
.tbl tbody tr:hover { background: var(--bg); }
.tbl .num { text-align: right; }
.mono { font-family: var(--font-mono); }
.nowrap { white-space: nowrap; }
.dim { color: #777; font-size: 12px; }
.strong { font-weight: 700; }
.link { text-decoration: underline; color: inherit; }
.details { max-width: 280px; color: #444; }

.tag {
  display: inline-block; border: var(--stroke); padding: 1px 7px; margin-right: 4px;
  font-size: 10px; font-weight: 800; text-transform: uppercase; background: var(--neutral);
}
.tag.court { background: var(--teal); }
.tag.lead { background: var(--surface); }
.tag.rush { background: var(--pink); color: #fff; }
.tag.status { background: #FF6B47; color: #fff; }

/* Coverage checkboxes — read-only indicators derived from the data, not inputs.
 * Ticked = we did the work; unticked = we have not, which is NOT "nothing found". */
.tbl .ctr { text-align: center; }
/* A real 2px-stroke box rather than ☐/☑ — the Unicode glyphs render hairline-thin
 * at this size and were near-invisible against the cream background. */
.box {
  display: inline-flex; align-items: center; justify-content: center;
  width: 20px; height: 20px; border: var(--stroke); background: var(--surface);
  cursor: help; vertical-align: middle;
}
.box.on { background: var(--teal); }
.tick { font-size: 14px; font-weight: 900; line-height: 1; color: var(--ink); }
.tiny { font-size: 10px; line-height: 1.3; margin-top: 2px; white-space: nowrap; }

@media (max-width: 768px) {
  .admin { padding: 14px; }
  .title { font-size: 26px; }
}
</style>
