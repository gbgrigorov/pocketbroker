<script setup>
/* How It Works — investor-pitch framing. Centerpiece is the EFFORT it takes to
   map one developer. Source-agnostic by design: we describe the *kinds* of
   sources (governmental register, court registry, web/forum search), never the
   specific sites. Numbers are typical averages drawn from real cases we mapped. */
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import StatTile from '../components/StatTile.vue'
import AppLink from '../components/AppLink.vue'
import { setPageMeta } from '../lib/pageMeta'

const { t } = useI18n()

/* Live database counts — the real haul, fetched from /api/stats. */
const counts = ref(null)
const fmt = (n) => new Intl.NumberFormat('en-US').format(n ?? 0)

/* Which counts to surface, in order, with their accent + i18n label key. */
const dbTiles = [
  { key: 'price_snapshots', labelKey: 'about.dbTiles.price_snapshots', accent: 'var(--coral)' },
  { key: 'entities',        labelKey: 'about.dbTiles.entities',        accent: 'var(--pink)' },
  { key: 'ownership_links', labelKey: 'about.dbTiles.ownership_links', accent: 'var(--teal)' },
  { key: 'builders',        labelKey: 'about.dbTiles.builders',        accent: 'var(--blue)' },
  { key: 'signals',         labelKey: 'about.dbTiles.signals',         accent: 'var(--coral)' },
  { key: 'neighbourhoods',  labelKey: 'about.dbTiles.neighbourhoods',  accent: 'var(--teal)' },
  { key: 'gold_prices',     labelKey: 'about.dbTiles.gold_prices',     accent: 'var(--pink)' },
  { key: 'cities',          labelKey: 'about.dbTiles.cities',          accent: 'var(--blue)' },
]

onMounted(async () => {
  setPageMeta({
    title: t('meta.aboutTitle'),
    description: t('meta.aboutDesc'),
  })
  try {
    const res = await api.stats()
    counts.value = res.counts
  } catch (e) {
    /* leave counts null — section stays hidden rather than showing zeros */
  }
})

/* The effort, by the numbers — `unit`/`sub` are i18n keys, `big` is a raw figure. */
const stats = [
  { big: '~30', unit: 'about.stats.spv.unit', sub: 'about.stats.spv.sub' },
  { big: '6–10', unit: 'about.stats.people.unit', sub: 'about.stats.people.sub' },
  { big: '3', unit: 'about.stats.registers.unit', sub: 'about.stats.registers.sub' },
  { big: '5+', unit: 'about.stats.web.unit', sub: 'about.stats.web.sub' },
  { big: '~120', unit: 'about.stats.lookups.unit', sub: 'about.stats.lookups.sub' },
  { big: '~60', unit: 'about.stats.searches.unit', sub: 'about.stats.searches.sub' },
  { big: '50–90K', unit: 'about.stats.words.unit', sub: 'about.stats.words.sub' },
  { big: '15–60', unit: 'about.stats.time.unit', sub: 'about.stats.time.sub' },
]

/* Pipeline steps — `t`/`d` hold i18n keys for title/description. */
const pipeline = [
  { n: '01', t: 'about.pipeline.s1.t', d: 'about.pipeline.s1.d' },
  { n: '02', t: 'about.pipeline.s2.t', d: 'about.pipeline.s2.d' },
  { n: '03', t: 'about.pipeline.s3.t', d: 'about.pipeline.s3.d' },
  { n: '04', t: 'about.pipeline.s4.t', d: 'about.pipeline.s4.d' },
  { n: '05', t: 'about.pipeline.s5.t', d: 'about.pipeline.s5.d' },
  { n: '06', t: 'about.pipeline.s6.t', d: 'about.pipeline.s6.d' },
]

const tiers = [
  { key: 'official', label: 'about.tiers.official.label', cls: 'official', desc: 'about.tiers.official.desc' },
  { key: 'community', label: 'about.tiers.community.label', cls: 'community', desc: 'about.tiers.community.desc' },
  { key: 'web', label: 'about.tiers.web.label', cls: 'web', desc: 'about.tiers.web.desc' },
]
</script>

<template>
  <div class="about">
    <!-- HERO -->
    <header class="hero">
      <div class="hero-copy">
        <div class="mono tag">{{ $t('about.tag') }}</div>
        <h1 class="display title" v-html="$t('about.title')"></h1>
        <p class="lede" v-html="$t('about.lede')"></p>
        <div class="hero-cta">
          <AppLink to="/entities" class="cta">{{ $t('about.heroCta') }}</AppLink>
        </div>
      </div>
      <figure class="hero-art">
        <img src="/how-to-network-example.png" alt="A sprawling ownership network: one parent company at the centre, hundreds of subsidiary companies fanning out in dense clusters, connected by ownership links — the real structure behind a single developer brand." />
        <figcaption class="mono">{{ $t('about.heroCaption') }}</figcaption>
      </figure>
    </header>

    <!-- PROBLEM -->
    <section class="band">
      <h2 class="display sec">{{ $t('about.problemTitle') }}</h2>
      <p class="band-lede big" v-html="$t('about.problemBody')"></p>
    </section>

    <!-- EFFORT — THE CENTERPIECE -->
    <section class="band effort">
      <h2 class="display sec" v-html="$t('about.effortTitle')"></h2>
      <p class="band-lede">{{ $t('about.effortLede') }}</p>

      <div class="stat-grid">
        <div v-for="s in stats" :key="s.unit" class="stat">
          <div class="stat-big display">{{ s.big }}</div>
          <div class="stat-unit label">{{ $t(s.unit) }}</div>
          <div class="stat-sub">{{ $t(s.sub) }}</div>
        </div>
      </div>

      <!-- The loop -->
      <div class="loop">
        <div class="loop-text">
          <h3 class="ch" v-html="$t('about.loopTitle')"></h3>
          <p v-html="$t('about.loopBody')"></p>
        </div>
        <div class="loop-cycle mono">{{ $t('about.loopCycle') }}</div>
      </div>

      <!-- The payoff comparison -->
      <div class="versus">
        <div class="vs-card manual">
          <div class="vs-label label">{{ $t('about.versusByHand') }}</div>
          <div class="vs-big display">{{ $t('about.versusByHandBig') }}</div>
          <div class="vs-sub">{{ $t('about.versusByHandSub') }}</div>
        </div>
        <div class="vs-arrow display">→</div>
        <div class="vs-card us">
          <div class="vs-label label">{{ $t('about.versusUs') }}</div>
          <div class="vs-big display">{{ $t('about.versusUsBig') }}</div>
          <div class="vs-sub">{{ $t('about.versusUsSub') }}</div>
        </div>
      </div>
      <p class="fineprint mono">{{ $t('about.fineprint') }}</p>
    </section>

    <!-- LIVE DATABASE — proof, not pitch -->
    <section v-if="counts" class="band">
      <h2 class="display sec" v-html="$t('about.dbTitle')"></h2>
      <p class="band-lede">{{ $t('about.dbLede') }}</p>
      <div class="db-grid">
        <StatTile
          v-for="tile in dbTiles"
          :key="tile.key"
          :value="fmt(counts[tile.key])"
          :label="$t(tile.labelKey)"
          :accent="tile.accent"
        />
      </div>
    </section>

    <!-- PIPELINE -->
    <section class="band">
      <h2 class="display sec">{{ $t('about.pipelineTitle') }}</h2>
      <p class="band-lede">{{ $t('about.pipelineLede') }}</p>
      <ol class="steps">
        <li v-for="s in pipeline" :key="s.n" class="step">
          <div class="step-n display">{{ s.n }}</div>
          <div class="step-body">
            <h3 class="ch">{{ $t(s.t) }}</h3>
            <p>{{ $t(s.d) }}</p>
          </div>
        </li>
      </ol>
    </section>

    <!-- SPV -->
    <section class="band">
      <h2 class="display sec">{{ $t('about.spvTitle') }}</h2>
      <article class="card wide">
        <p v-html="$t('about.spvBody')"></p>
        <p class="note mono">{{ $t('about.spvNote') }}</p>
      </article>
    </section>

    <!-- DIAGRAM -->
    <section class="band">
      <h2 class="display sec">{{ $t('about.diagramTitle') }}</h2>
      <p class="band-lede">{{ $t('about.diagramLede') }}</p>
      <figure class="diagram">
        <img src="/ownership-example.svg" alt="Ownership graph: an ultimate owner controls a holding company, which controls the brand/builder, which fans out into project SPVs. A shared co-manager links the brand to a disputed SPV. Three evidence notes — an official court record, a community forum report, and a web mention — are attached to that SPV." />
        <figcaption class="mono">{{ $t('about.diagramCaption') }}</figcaption>
      </figure>
    </section>

    <!-- TIERS -->
    <section class="band">
      <h2 class="display sec">{{ $t('about.tiersTitle') }}</h2>
      <div class="cards three">
        <article v-for="tier in tiers" :key="tier.key" class="card tier">
          <div class="tier-head" :class="tier.cls">{{ $t(tier.label) }}</div>
          <p>{{ $t(tier.desc) }}</p>
        </article>
      </div>
    </section>

    <!-- DISCLAIMER -->
    <section class="band">
      <article class="card disclaimer">
        <h2 class="display sec warned">{{ $t('about.disclaimerTitle') }}</h2>
        <p v-html="$t('about.disclaimerBody')"></p>
        <ul class="bullets">
          <li v-html="$t('about.disclaimerB1')"></li>
          <li>{{ $t('about.disclaimerB2') }}</li>
        </ul>
      </article>
    </section>

    <!-- CTA -->
    <section class="band cta-band">
      <h2 class="display sec">{{ $t('about.ctaTitle') }}</h2>
      <div class="ctas">
        <AppLink to="/entities" class="cta">{{ $t('about.ctaBrowse') }}</AppLink>
        <AppLink to="/" class="cta ghost">{{ $t('about.ctaMap') }}</AppLink>
      </div>
    </section>

    <footer class="foot mono">{{ $t('about.foot') }}</footer>
  </div>
</template>

<style scoped>
.about { max-width: 960px; margin: 0 auto; padding: 40px 28px 72px; }
:deep(.hl) { color: var(--pink); }

/* HERO */
.hero {
  margin-bottom: 12px;
  display: grid;
  grid-template-columns: 3fr 2fr;   /* ~60 / 40 — text left, network art right */
  gap: 32px;
  align-items: center;
}
.hero-copy { min-width: 0; }
.tag { font-size: 11px; color: #555; }
.title { font-size: 56px; line-height: 0.92; margin: 12px 0 18px; }
.lede { font-size: 18px; line-height: 1.5; max-width: 52ch; margin: 0; }
.hero-cta { margin-top: 22px; }
.hero-art { margin: 0; }
.hero-art img {
  width: 100%; height: auto; display: block;
  background: var(--bg); border: var(--stroke); box-shadow: var(--shadow-lg);
}
.hero-art figcaption { font-size: 10px; color: #777; margin-top: 8px; text-align: right; }

/* Bands */
.band { margin-top: 52px; }
.sec { font-size: 27px; border-bottom: var(--stroke); padding-bottom: 6px; margin-bottom: 18px; }
.band-lede { font-size: 16px; line-height: 1.55; max-width: 66ch; margin: 0 0 22px; }
.band-lede.big { font-size: 19px; max-width: 64ch; }

/* EFFORT */
.effort {
  background: var(--ink);
  color: var(--bg);
  margin-left: -28px; margin-right: -28px;
  padding: 36px 28px 30px;
  border-top: var(--stroke-thick); border-bottom: var(--stroke-thick);
}
.effort .sec { color: var(--bg); border-bottom-color: var(--bg); }
.effort .band-lede { color: #e9e1c8; }

.stat-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px;
}

/* Live DB counts grid */
.db-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px;
}
.stat {
  background: var(--surface); color: var(--ink);
  border: var(--stroke); box-shadow: var(--shadow);
  padding: 14px 14px 16px;
}
.stat-big { font-size: 46px; line-height: 0.9; color: var(--coral); }
.stat-unit { margin-top: 6px; }
.stat-sub { font-size: 11px; line-height: 1.4; color: #555; margin-top: 6px; }

/* Loop */
.loop {
  margin-top: 22px; display: grid; grid-template-columns: 1fr; gap: 14px;
  background: #1c1c1c; border: var(--stroke); border-color: var(--coral); padding: 18px;
}
.loop .ch { color: var(--bg); font-size: 21px; }
.loop p { color: #e9e1c8; font-size: 14px; line-height: 1.55; margin: 8px 0 0; max-width: 70ch; }
.loop-cycle {
  font-size: 13px; color: var(--teal); background: #0d0d0d;
  border: var(--stroke); border-color: #333; padding: 10px 12px; text-align: center;
  letter-spacing: 0.02em;
}

/* Versus */
.versus {
  margin-top: 22px; display: grid; grid-template-columns: 1fr auto 1fr; gap: 14px; align-items: center;
}
.vs-card { border: var(--stroke); box-shadow: var(--shadow); padding: 18px; text-align: center; }
.vs-card.manual { background: var(--surface); color: var(--ink); }
.vs-card.us { background: var(--pink); color: #fff; border-color: #fff; }
.vs-label { font-size: 11px; opacity: 0.8; }
.vs-big { font-size: 40px; line-height: 1; margin: 6px 0; }
.vs-sub { font-size: 12px; line-height: 1.4; }
.vs-arrow { font-size: 36px; color: var(--bg); }
.fineprint { margin-top: 14px; font-size: 10px; color: #998f73; }

/* Cards */
.cards { display: grid; gap: 16px; }
.cards.three { grid-template-columns: repeat(3, 1fr); }
.card { background: var(--surface); border: var(--stroke); box-shadow: var(--shadow); padding: 18px; }
.card p { font-size: 14px; line-height: 1.5; margin: 8px 0 0; }
.card.wide p { font-size: 15px; }
.ch { font-size: 19px; margin: 0; }

/* Steps */
.steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }
.step {
  display: grid; grid-template-columns: 60px 1fr; gap: 16px; align-items: start;
  background: var(--surface); border: var(--stroke); box-shadow: var(--shadow); padding: 16px 18px;
}
.step-n { font-size: 32px; line-height: 1; color: var(--pink); }
.step-body p { font-size: 14px; line-height: 1.5; margin: 6px 0 0; }

/* Tiers */
.tier { display: flex; flex-direction: column; gap: 10px; }
.tier-head {
  align-self: flex-start; font-family: var(--font-display); font-weight: 800;
  text-transform: uppercase; font-size: 13px; letter-spacing: 0.04em; padding: 4px 9px; border: var(--stroke);
}
.tier-head.official { background: var(--pink); color: #fff; }
.tier-head.community { background: var(--coral); color: #fff; }
.tier-head.web { background: var(--neutral); }
.tier p { font-size: 13px; line-height: 1.5; margin: 0; }

/* Diagram */
.diagram { margin: 0; }
.diagram img {
  width: 100%; height: auto; display: block;
  background: var(--bg); border: var(--stroke); box-shadow: var(--shadow);
}
.diagram figcaption { font-size: 11px; color: #777; margin-top: 8px; }

/* SPV note */
.note {
  font-size: 12px; line-height: 1.5; background: var(--bg);
  border-left: 4px solid var(--ink); padding: 10px 12px; margin-top: 14px;
}

/* Disclaimer */
.disclaimer { background: #FFF8EC; border-top: 6px solid #b22; }
.sec.warned { color: #b22; border-bottom-color: #b22; }
.bullets { margin: 12px 0 0; padding-left: 18px; }
.bullets li { font-size: 14px; line-height: 1.5; margin-bottom: 8px; }

/* CTA */
.cta-band { margin-top: 52px; }
.ctas { display: flex; gap: 14px; flex-wrap: wrap; }
.cta {
  display: inline-block; text-decoration: none; cursor: pointer;
  background: var(--pink); color: #fff; border: var(--stroke); box-shadow: var(--shadow);
  padding: 13px 18px; font-weight: 700; font-size: 15px; transition: transform 0.08s ease;
}
.cta:active { transform: translate(2px, 2px); box-shadow: 2px 2px 0 0 var(--ink); }
.cta.ghost { background: var(--surface); color: var(--ink); }

.foot { margin-top: 52px; padding-top: 16px; border-top: var(--stroke); font-size: 11px; color: #777; }

@media (max-width: 820px) {
  .hero { grid-template-columns: 1fr; gap: 22px; }
  .hero-art figcaption { text-align: left; }
  .title { font-size: 42px; }
  .stat-grid { grid-template-columns: repeat(2, 1fr); }
  .db-grid { grid-template-columns: repeat(2, 1fr); }
  .cards.three { grid-template-columns: 1fr; }
  .versus { grid-template-columns: 1fr; }
  .vs-arrow { transform: rotate(90deg); justify-self: center; }
}
</style>
