<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import * as d3 from 'd3'
import { ptrVerdict, PTR_TONE_COLOR } from '../lib/finance'

const props = defineProps({ series: Array }) // [{ period_date, ptr }]
const el = ref(null)
const { t, locale } = useI18n()

// Verdict bands (same 7-tier scale as ptrVerdict) drawn as horizontal zones.
// labelKey is resolved with t() at render so the bands follow the active locale.
const BANDS = [
  { from: 0, to: 12, tone: 'buy', labelKey: 'finance.verdict.strongBuy' },
  { from: 12, to: 15, tone: 'good', labelKey: 'finance.verdict.goodValue' },
  { from: 15, to: 18, tone: 'fair', labelKey: 'finance.verdict.fair' },
  { from: 18, to: 20, tone: 'stretched', labelKey: 'finance.verdict.stretched' },
  { from: 20, to: 25, tone: 'expensive', labelKey: 'finance.verdict.expensive' },
  { from: 25, to: 30, tone: 'overpriced', labelKey: 'finance.verdict.overpriced' },
  { from: 30, to: Infinity, tone: 'extreme', labelKey: 'finance.verdict.extreme' },
]

function render() {
  const host = el.value
  if (!host) return
  host.innerHTML = ''
  const data = (props.series || [])
    .map((d) => ({ date: new Date(d.period_date), v: d.ptr }))
    .filter((d) => d.v != null && isFinite(d.v))

  if (data.length === 0) {
    const msg = document.createElement('div')
    msg.className = 'empty label'
    msg.textContent = t('ptrChart.noData')
    host.appendChild(msg)
    return
  }

  const w = host.clientWidth || 320
  const h = 200
  const m = { top: 10, right: 66, bottom: 22, left: 30 }

  // Domain top reaches at least into the "extreme" band so every zone is visible.
  const yTop = Math.max(34, d3.max(data, (d) => d.v) * 1.1)
  const x =
    data.length > 1
      ? d3.scaleTime().domain(d3.extent(data, (d) => d.date)).range([m.left, w - m.right])
      : d3.scaleTime().domain([data[0].date, data[0].date]).range([m.left, w - m.right])
  const y = d3.scaleLinear().domain([0, yTop]).range([h - m.bottom, m.top])

  const svg = d3.select(host).append('svg').attr('width', w).attr('height', h)

  // verdict bands (flat fills, behind the line)
  BANDS.forEach((b) => {
    if (b.from >= yTop) return
    const top = Math.min(b.to, yTop)
    const yTopPx = y(top)
    const yBotPx = y(b.from)
    svg
      .append('rect')
      .attr('x', m.left)
      .attr('y', yTopPx)
      .attr('width', Math.max(0, w - m.right - m.left))
      .attr('height', Math.max(0, yBotPx - yTopPx))
      .style('fill', PTR_TONE_COLOR[b.tone])
      .style('fill-opacity', 0.5)
    // band label in the right margin (cream background → always readable)
    if (yBotPx - yTopPx > 11) {
      svg
        .append('text')
        .attr('x', w - m.right + 5)
        .attr('y', (yTopPx + yBotPx) / 2 + 3)
        .style('font-family', 'var(--font-mono)')
        .style('font-size', '8.5px')
        .style('fill', 'var(--ink)')
        .text(t(b.labelKey))
    }
  })

  // axes (flat, mono labels)
  svg
    .append('g')
    .attr('transform', `translate(0,${h - m.bottom})`)
    .call(d3.axisBottom(x).ticks(5).tickFormat(d3.timeFormat('%Y')).tickSizeOuter(0))
    .call((g) => g.selectAll('text').style('font-family', 'var(--font-mono)').attr('font-size', 10))

  svg
    .append('g')
    .attr('transform', `translate(${m.left},0)`)
    .call(d3.axisLeft(y).ticks(5).tickSizeOuter(0))
    .call((g) => g.selectAll('text').style('font-family', 'var(--font-mono)').attr('font-size', 10))

  // line — white halo under an ink stroke so it reads over every band colour
  if (data.length > 1) {
    const line = d3
      .line()
      .x((d) => x(d.date))
      .y((d) => y(d.v))
      .curve(d3.curveMonotoneX)
    svg
      .append('path')
      .datum(data)
      .attr('fill', 'none')
      .style('stroke', '#fff')
      .attr('stroke-width', 5)
      .attr('d', line)
    svg
      .append('path')
      .datum(data)
      .attr('fill', 'none')
      .style('stroke', 'var(--ink)')
      .attr('stroke-width', 2.5)
      .attr('d', line)
  }

  // end marker, coloured by its verdict
  const last = data[data.length - 1]
  svg
    .append('circle')
    .attr('cx', x(last.date))
    .attr('cy', y(last.v))
    .attr('r', 5)
    .style('fill', PTR_TONE_COLOR[ptrVerdict(last.v).tone])
    .style('stroke', 'var(--ink)')
    .style('stroke-width', 2)

  // --- interactive hover: crosshair + focus dot + tooltip ---
  const focus = svg.append('g').style('display', 'none')
  focus
    .append('line')
    .attr('class', 'focus-line')
    .attr('y1', m.top)
    .attr('y2', h - m.bottom)
    .style('stroke', 'var(--ink)')
    .style('stroke-width', 1)
    .style('stroke-dasharray', '3,3')
  const focusDot = focus
    .append('circle')
    .attr('r', 4.5)
    .style('stroke', 'var(--ink)')
    .style('stroke-width', 2)
  const tip = focus.append('g')
  const tipBg = tip.append('rect').attr('height', 32).attr('rx', 0).style('fill', 'var(--ink)')
  const tipVal = tip
    .append('text')
    .attr('x', 8)
    .attr('y', 13)
    .style('font-family', 'var(--font-mono)')
    .style('font-size', '11px')
    .style('font-weight', 700)
    .style('fill', '#fff')
  const tipDate = tip
    .append('text')
    .attr('x', 8)
    .attr('y', 26)
    .style('font-family', 'var(--font-mono)')
    .style('font-size', '10px')
    .style('fill', 'var(--bg)')

  const bisect = d3.bisector((d) => d.date).center
  const fmtDate = d3.timeFormat('%b %Y')

  svg
    .append('rect')
    .attr('x', m.left)
    .attr('y', m.top)
    .attr('width', Math.max(0, w - m.right - m.left))
    .attr('height', Math.max(0, h - m.bottom - m.top))
    .style('fill', 'transparent')
    .style('cursor', 'crosshair')
    .on('pointerenter pointermove', (event) => {
      const mx = d3.pointer(event)[0]
      const d = data[bisect(data, x.invert(mx))]
      if (!d) return
      focus.style('display', null)
      const px = x(d.date)
      const py = y(d.v)
      const verdict = ptrVerdict(d.v)
      focus.select('.focus-line').attr('x1', px).attr('x2', px)
      focusDot.attr('cx', px).attr('cy', py).style('fill', PTR_TONE_COLOR[verdict.tone])
      tipVal.text(d.v.toFixed(1) + ' · ' + t(verdict.labelKey))
      tipDate.text(fmtDate(d.date))
      const tw =
        Math.max(tipVal.node().getComputedTextLength(), tipDate.node().getComputedTextLength()) + 16
      tipBg.attr('width', tw)
      const tx = px + 10 + tw > w ? px - 10 - tw : px + 10
      tip.attr('transform', `translate(${tx},${Math.max(m.top, py - 38)})`)
    })
    .on('pointerleave', () => focus.style('display', 'none'))
}

let ro = null
onMounted(() => {
  render()
  // Re-measure when the card reflows (phone rotation, breakpoint changes).
  ro = new ResizeObserver(render)
  ro.observe(el.value)
})
onBeforeUnmount(() => ro?.disconnect())
watch(() => props.series, render)
watch(locale, render) // redraw band/tooltip labels when the language changes
</script>

<template>
  <div ref="el" class="chart"></div>
</template>

<style scoped>
.chart {
  width: 100%;
}
.chart :deep(.domain),
.chart :deep(.tick line) {
  stroke: var(--ink);
}
.chart .empty {
  padding: 40px 12px;
  text-align: center;
  color: #999;
}
</style>
