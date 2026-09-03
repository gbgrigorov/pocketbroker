<script setup>
/* Hidden client deliverable: a professional, print-ready research report.
 * Rendered from an authored report object (src/reports, keyed by ЕИК) — a
 * point-in-time snapshot, not live-bound. Generic over any registered entity. */
import { computed } from 'vue'
import { getReport } from '../reports'
import { entityPath } from '../router'
import AppLink from '../components/AppLink.vue'

const props = defineProps({ ekey: String, slug: String })
const report = computed(() => getReport(props.ekey))

function printReport() { window.print() }

// Deterministic hub-and-spoke ownership diagram (UBO → companies), laid out in
// rows of 3. Static SVG so it is self-contained (no API/auth) and prints cleanly.
const net = computed(() => {
  const r = report.value
  if (!r) return null
  const ents = r.ownership.entities
  const COLS = 3
  const PAD = 12
  const nodeW = 212, nodeH = 92, gapX = 30, gapY = 46
  const personW = 256, personH = 58
  const rows = Math.ceil(ents.length / COLS)
  const contentW = COLS * nodeW + (COLS - 1) * gapX
  const svgW = contentW + PAD * 2
  const firstRowY = PAD + personH + 66
  const svgH = firstRowY + rows * nodeH + (rows - 1) * gapY + PAD
  const personX = (svgW - personW) / 2
  const nodes = ents.map((e, i) => {
    const c = i % COLS, rr = Math.floor(i / COLS)
    const x = PAD + c * (nodeW + gapX)
    const y = firstRowY + rr * (nodeH + gapY)
    return { ...e, x, y, w: nodeW, h: nodeH, cx: x + nodeW / 2 }
  })
  return {
    svgW, svgH, personX, personY: PAD, personW, personH,
    personCx: svgW / 2, personBottom: PAD + personH, ubo: r.ownership.ubo, nodes,
  }
})
</script>

<template>
  <div v-if="report" class="reportwrap">
    <!-- Screen-only action bar (hidden in print) -->
    <div class="actionbar noprint">
      <AppLink :to="entityPath(ekey, slug)" class="abtn">← Профил</AppLink>
      <span class="aref mono">{{ report.meta.refNo }}</span>
      <button class="abtn primary" @click="printReport">Печат / Запази като PDF</button>
    </div>

    <article class="sheet">
      <!-- Letterhead -->
      <header class="lh">
        <div class="lh__top">
          <span class="lh__class mono">{{ report.meta.classification }}</span>
          <span class="lh__ref mono">Реф. № {{ report.meta.refNo }} · {{ report.meta.reportDate }}</span>
        </div>
        <h1 class="lh__title display">{{ report.meta.title }}</h1>
        <p class="lh__sub">{{ report.meta.subtitle }}</p>
        <div class="lh__subject">
          <span class="lh__subject-label label">Обект на анализа</span>
          <span class="lh__subject-name">{{ report.subject.name }}</span>
          <span class="lh__subject-eik mono">ЕИК {{ report.subject.eik }}</span>
        </div>
      </header>

      <!-- AI notice — frames the whole document -->
      <div v-if="report.meta.aiNotice" class="ainote avoid-break">
        <span class="ainote__tag display">AI</span>
        <p class="ainote__txt">{{ report.meta.aiNotice }}</p>
      </div>

      <!-- 1. Резюме -->
      <section class="sec avoid-break">
        <h2 class="sec__h display"><span class="sec__n">1</span> Резюме</h2>
        <p v-for="(p, i) in report.summary" :key="'sum' + i" class="para">{{ p }}</p>
      </section>

      <!-- 2. Идентификация -->
      <section class="sec avoid-break">
        <h2 class="sec__h display"><span class="sec__n">2</span> Идентификация на дружеството</h2>
        <table class="facts">
          <tbody>
            <tr v-for="(row, i) in report.subject.rows" :key="'sub' + i">
              <th>{{ row[0] }}</th>
              <td>{{ row[1] }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- 3. Собственост и контрол -->
      <section class="sec">
        <h2 class="sec__h display"><span class="sec__n">3</span> Собственост и свързани лица</h2>
        <div class="ubo">
          <span class="label">Собственик и управител</span>
          <span class="ubo__name">{{ report.ownership.ubo }}</span>
        </div>

        <!-- Network diagram: deterministic SVG, self-contained, print-friendly -->
        <figure v-if="net" class="netfig avoid-break">
          <svg class="net" :viewBox="`0 0 ${net.svgW} ${net.svgH}`" :style="{ maxWidth: net.svgW + 'px' }" role="img" aria-label="Карта на собствеността">
            <line
              v-for="n in net.nodes" :key="'edge' + n.eik"
              :x1="net.personCx" :y1="net.personBottom" :x2="n.cx" :y2="n.y"
              class="net__edge"
            />
            <foreignObject :x="net.personX" :y="net.personY" :width="net.personW" :height="net.personH">
              <div xmlns="http://www.w3.org/1999/xhtml" class="nnode nnode--person">
                <div class="nnode__name">{{ net.ubo }}</div>
                <div class="nnode__role">едноличен собственик · управител</div>
              </div>
            </foreignObject>
            <foreignObject v-for="n in net.nodes" :key="'node' + n.eik" :x="n.x" :y="n.y" :width="n.w" :height="n.h">
              <div xmlns="http://www.w3.org/1999/xhtml" class="nnode nnode--co" :class="{ 'is-subject': n.highlight, 'has-cases': n.cases }">
                <div class="nnode__co">{{ n.name }}</div>
                <div class="nnode__meta">ЕИК {{ n.eik }} · {{ n.capital }}</div>
                <div v-if="n.cases" class="nnode__badge">⚖ {{ n.cases }} {{ n.cases === 1 ? 'дело' : 'дела' }}</div>
              </div>
            </foreignObject>
          </svg>
          <figcaption class="netfig__cap mono">{{ report.ownership.figCaption || 'Фиг. 1 — Карта на собствеността. Розово = обект на анализа; ⚖ = открити съдебни дела.' }}</figcaption>
        </figure>

        <p v-for="(p, i) in report.ownership.narrative" :key="'own' + i" class="para">{{ p }}</p>
        <table class="grid-tbl">
          <thead>
            <tr><th>ЕИК</th><th>Наименование</th><th>Капитал</th><th>Вписано</th><th>Бележка</th></tr>
          </thead>
          <tbody>
            <tr v-for="e in report.ownership.entities" :key="e.eik" :class="{ hl: e.highlight }">
              <td class="mono">{{ e.eik }}</td>
              <td>{{ e.name }}</td>
              <td class="mono nowrap">{{ e.capital }}</td>
              <td class="mono nowrap">{{ e.registered }}</td>
              <td class="note">{{ e.note }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="report.ownership.note" class="footnote">{{ report.ownership.note }}</p>
      </section>

      <!-- 4. Официални съдебни записи -->
      <section class="sec">
        <h2 class="sec__h display"><span class="sec__n">4</span> Официални съдебни записи</h2>
        <p class="para">{{ report.court.intro }}</p>
        <div v-for="(c, i) in report.court.cases" :key="'case' + i" class="case avoid-break">
          <div class="case__head">
            <span class="case__no display">{{ c.caseNo }}</span>
            <span class="case__court">{{ c.court }}</span>
            <span class="case__role" :class="c.role === 'ответник' ? 'def' : 'plf'">{{ c.role }}</span>
          </div>
          <div class="case__meta mono">{{ c.act }} · {{ c.caseType }} · страна: {{ c.party }}</div>
          <p class="case__sum">{{ c.summary }}</p>
          <div class="case__outcome"><span class="label">Изход</span> {{ c.outcome }}</div>
          <a :href="c.url" target="_blank" rel="noopener" class="case__src mono noprint">Източник ↗</a>
          <div class="case__src-print mono">{{ c.url }}</div>
        </div>
        <p v-if="report.court.excluded" class="footnote"><strong>Изключено:</strong> {{ report.court.excluded }}</p>
        <p v-if="report.court.note" class="footnote">{{ report.court.note }}</p>
      </section>

      <!-- 5. Публични / медийни сигнали -->
      <section class="sec avoid-break">
        <h2 class="sec__h display"><span class="sec__n">5</span> Публични и медийни сигнали</h2>
        <p class="para" :class="{ none: !report.media.found }">{{ report.media.note }}</p>
      </section>

      <!-- 6. Какво си заслужава по-нататъшна проверка -->
      <section class="sec">
        <h2 class="sec__h display"><span class="sec__n">6</span> Какво си заслужава по-нататъшна проверка</h2>
        <div class="obs">
          <div v-for="(o, i) in report.analysis" :key="'obs' + i" class="obs__item avoid-break">
            <h3 class="obs__t">{{ o.title }}</h3>
            <p class="obs__b">{{ o.body }}</p>
          </div>
        </div>
        <p class="ainline">⚠ Изводите по-горе са генерирани от AI върху публична информация и са само отправна точка за вашето проучване — не са присъда и не доказват нарушение.</p>
      </section>

      <!-- 7. Методология -->
      <section class="sec avoid-break">
        <h2 class="sec__h display"><span class="sec__n">7</span> Методология</h2>
        <ol class="method">
          <li v-for="(m, i) in report.methodology" :key="'m' + i">{{ m }}</li>
        </ol>
      </section>

      <!-- 8. Източници -->
      <section class="sec avoid-break">
        <h2 class="sec__h display"><span class="sec__n">8</span> Източници</h2>
        <ul class="sources">
          <li v-for="(s, i) in report.sources" :key="'s' + i">
            <span class="src__label">{{ s.label }}</span>
            <a :href="s.url" target="_blank" rel="noopener" class="src__url mono">{{ s.url }}</a>
          </li>
        </ul>
      </section>

      <!-- Disclaimer -->
      <footer class="disc avoid-break">
        <span class="label">Уговорки и ограничения</span>
        <p>{{ report.disclaimer }}</p>
        <div class="disc__foot mono">
          {{ report.meta.classification }} · Реф. № {{ report.meta.refNo }} · {{ report.meta.reportDate }}
        </div>
      </footer>
    </article>
  </div>

  <div v-else class="missing">
    <h1 class="display">Няма наличен доклад</h1>
    <p>За тази фирма все още не е изготвен доклад.</p>
    <AppLink :to="entityPath(ekey, slug)" class="abtn">← Към профила</AppLink>
  </div>
</template>

<style scoped>
/* ── Screen shell ─────────────────────────────────────────────── */
.reportwrap { background: #d8d2c0; min-height: 100vh; padding: 0 0 60px; }

.actionbar {
  position: sticky; top: 0; z-index: 10;
  display: flex; align-items: center; gap: 14px;
  padding: 12px 20px; background: var(--surface); border-bottom: var(--stroke-thick);
}
.aref { margin-left: auto; font-size: 12px; color: #666; }
.abtn {
  border: var(--stroke); background: var(--surface); box-shadow: var(--shadow);
  padding: 7px 14px; font-weight: 700; font-family: var(--font-head);
  text-decoration: none; color: var(--ink); cursor: pointer; font-size: 13px;
}
.abtn:active { transform: translate(2px, 2px); box-shadow: 2px 2px 0 0 var(--ink); }
.abtn.primary { background: var(--pink); color: #fff; }

/* ── The A4 sheet ─────────────────────────────────────────────── */
.sheet {
  width: 210mm; max-width: 100%;
  margin: 28px auto; padding: 22mm 20mm;
  background: #fff; color: var(--ink);
  box-shadow: var(--shadow-lg);
  font-size: 11.5px; line-height: 1.55;
  box-sizing: border-box;
}

/* Letterhead */
.lh { border-bottom: var(--stroke-thick); padding-bottom: 16px; margin-bottom: 22px; }
.lh__top { display: flex; justify-content: space-between; font-size: 10px; letter-spacing: 0.05em; }
.lh__class { font-weight: 700; color: var(--pink); }
.lh__ref { color: #666; }
.lh__title { font-size: 30px; line-height: 1.02; margin: 14px 0 4px; }
.lh__sub { margin: 0; font-size: 12.5px; color: #555; }
.lh__subject {
  display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap;
  margin-top: 16px; padding: 10px 12px; border: var(--stroke); background: #faf7ee;
}
.lh__subject-label { color: #888; }
.lh__subject-name { font-family: var(--font-display); font-weight: 800; font-size: 18px; text-transform: uppercase; }
.lh__subject-eik { font-size: 12px; color: #444; margin-left: auto; }

/* AI notice */
.ainote {
  display: flex; gap: 12px; align-items: flex-start;
  border: var(--stroke); background: #fff3d6; padding: 10px 12px; margin: 0 0 22px;
}
.ainote__tag {
  flex: none; background: var(--ink); color: #fff; font-size: 13px;
  padding: 3px 8px; line-height: 1.1;
}
.ainote__txt { margin: 0; font-size: 10.5px; line-height: 1.5; color: #4a4326; }

/* Network diagram */
.netfig { margin: 4px 0 14px; }
.net { width: 100%; height: auto; display: block; }
.net__edge { stroke: var(--ink); stroke-width: 1.6; }
.nnode {
  height: 100%; box-sizing: border-box; border: var(--stroke); background: #fff;
  padding: 6px 9px; font-family: var(--font-head); overflow: hidden;
}
.nnode--person {
  background: var(--coral); color: #fff; text-align: center;
  display: flex; flex-direction: column; justify-content: center;
}
.nnode__name { font-family: var(--font-display); font-weight: 800; font-size: 14px; text-transform: uppercase; line-height: 1.05; }
.nnode__role { font-size: 9px; opacity: 0.92; margin-top: 2px; }
.nnode--co { display: flex; flex-direction: column; gap: 2px; }
.nnode--co.is-subject { background: #fff2d6; border-color: var(--pink); border-width: 3px; }
.nnode__co { font-weight: 700; font-size: 11px; line-height: 1.12; }
.nnode__meta { font-family: var(--font-mono); font-size: 8.5px; color: #666; }
.nnode__badge {
  margin-top: auto; align-self: flex-start; font-size: 9px; font-weight: 700;
  background: var(--pink); color: #fff; padding: 0 5px; border: 1.5px solid var(--ink);
}
.netfig__cap { font-size: 9px; color: #777; margin-top: 7px; line-height: 1.4; }

/* Sections */
.sec { margin: 0 0 22px; }
.sec__h {
  font-size: 16px; letter-spacing: 0.01em;
  border-bottom: var(--stroke); padding-bottom: 5px; margin-bottom: 12px;
  display: flex; align-items: center; gap: 10px;
}
.sec__n {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; background: var(--ink); color: #fff;
  font-size: 13px; flex: none;
}
.para { margin: 0 0 9px; text-align: justify; }
.para.none { color: #777; font-style: italic; }

/* Facts table */
.facts { width: 100%; border-collapse: collapse; }
.facts th, .facts td { border: var(--stroke); padding: 6px 9px; text-align: left; vertical-align: top; }
.facts th { width: 38%; background: #f3efe3; font-weight: 700; font-size: 11px; }

/* UBO callout */
.ubo { display: flex; align-items: baseline; gap: 12px; margin: 0 0 12px; padding: 8px 12px; border-left: 4px solid var(--pink); background: #faf7ee; }
.ubo__name { font-family: var(--font-display); font-weight: 800; font-size: 16px; text-transform: uppercase; }

/* Entity grid table */
.grid-tbl { width: 100%; border-collapse: collapse; margin: 4px 0 8px; }
.grid-tbl th, .grid-tbl td { border: var(--stroke); padding: 5px 8px; text-align: left; vertical-align: top; font-size: 10.5px; }
.grid-tbl thead th { background: var(--ink); color: #fff; font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; }
.grid-tbl tr.hl td { background: #fff2d6; font-weight: 600; }
.grid-tbl .note { font-size: 10px; color: #555; }
.nowrap { white-space: nowrap; }

/* Court cases */
.case { border: var(--stroke); box-shadow: 3px 3px 0 0 var(--ink); padding: 11px 13px; margin: 12px 0; background: #fff; }
.case__head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.case__no { font-size: 15px; }
.case__court { font-size: 12px; color: #444; }
.case__role { margin-left: auto; font-size: 10px; font-weight: 700; text-transform: uppercase; border: var(--stroke); padding: 1px 7px; }
.case__role.def { background: var(--pink); color: #fff; }
.case__role.plf { background: var(--neutral); }
.case__meta { font-size: 10px; color: #777; margin: 4px 0 7px; }
.case__sum { margin: 0 0 8px; text-align: justify; }
.case__outcome { font-size: 11px; background: #f3efe3; border-left: 3px solid var(--ink); padding: 5px 9px; }
.case__outcome .label { display: block; color: #888; margin-bottom: 1px; }
.case__src { display: inline-block; margin-top: 7px; font-size: 11px; color: var(--blue); }
.case__src-print { display: none; font-size: 9px; color: #666; margin-top: 6px; word-break: break-all; }

/* Observations */
.obs { display: grid; gap: 10px; }
.obs__item { border-left: 4px solid var(--coral); padding: 4px 0 4px 12px; }
.obs__t { font-size: 13px; font-weight: 700; margin: 0 0 3px; }
.obs__b { margin: 0; text-align: justify; }

/* Method / sources */
.method { margin: 0; padding-left: 20px; }
.method li { margin: 0 0 6px; text-align: justify; }
.sources { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.sources li { border-left: 3px solid var(--ink); padding-left: 9px; }
.src__label { display: block; font-size: 11px; font-weight: 600; }
.src__url { font-size: 9.5px; color: var(--blue); word-break: break-all; }

.footnote { font-size: 10px; color: #666; margin: 8px 0 0; font-style: italic; }
.ainline { font-size: 10px; color: #8a6d00; background: #fff3d6; border-left: 3px solid var(--coral); padding: 7px 10px; margin: 12px 0 0; line-height: 1.45; }

/* Disclaimer */
.disc { border: var(--stroke); background: #faf7ee; padding: 12px 14px; margin-top: 26px; }
.disc p { margin: 4px 0 0; font-size: 10px; color: #444; text-align: justify; line-height: 1.5; }
.disc__foot { margin-top: 10px; padding-top: 8px; border-top: 1px dashed #bbb; font-size: 9px; color: #777; text-align: center; }

/* Missing report */
.missing { padding: 80px 24px; text-align: center; }
.missing h1 { font-size: 30px; margin-bottom: 10px; }
.missing p { color: #555; margin-bottom: 20px; }

@media (max-width: 768px) {
  .sheet { width: 100%; margin: 0; padding: 18px 16px; box-shadow: none; }
  .lh__title { font-size: 24px; }
}

/* ── Print: clean A4, hide chrome ─────────────────────────────── */
@media print {
  .reportwrap { background: #fff; padding: 0; }
  .sheet { width: auto; margin: 0; padding: 0; box-shadow: none; font-size: 10.5pt; }
  .noprint { display: none !important; }
  .case__src-print { display: block; }
  .case { box-shadow: none; }
  .avoid-break { break-inside: avoid; }
  .sec { break-inside: auto; }
  .sec__h { break-after: avoid; }
  a { color: var(--ink); text-decoration: none; }
}
</style>
