<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as d3 from 'd3'

const props = defineProps({ series: Array }) // [{ period_date, price_eur_sqm }]
const el = ref(null)

function render() {
  const host = el.value
  if (!host) return
  host.innerHTML = ''
  const data = (props.series || [])
    .map((d) => ({ date: new Date(d.period_date), v: d.price_eur_sqm }))
    .filter((d) => !isNaN(d.v))
  if (data.length < 2) return

  const w = host.clientWidth || 320
  const h = 150
  const m = { top: 10, right: 8, bottom: 22, left: 44 }

  const x = d3.scaleTime().domain(d3.extent(data, (d) => d.date)).range([m.left, w - m.right])
  const y = d3
    .scaleLinear()
    .domain([0, d3.max(data, (d) => d.v) * 1.1])
    .range([h - m.bottom, m.top])

  const svg = d3.select(host).append('svg').attr('width', w).attr('height', h)

  // axes (flat, mono labels)
  svg
    .append('g')
    .attr('transform', `translate(0,${h - m.bottom})`)
    .call(d3.axisBottom(x).ticks(5).tickFormat(d3.timeFormat('%Y')).tickSizeOuter(0))
    .call((g) => g.selectAll('text').style('font-family', 'var(--font-mono)').attr('font-size', 10))

  svg
    .append('g')
    .attr('transform', `translate(${m.left},0)`)
    .call(d3.axisLeft(y).ticks(4).tickFormat((d) => '€' + d3.format('~s')(d)).tickSizeOuter(0))
    .call((g) => g.selectAll('text').style('font-family', 'var(--font-mono)').attr('font-size', 10))

  // line — flat, no fill, no gradient
  const line = d3
    .line()
    .x((d) => x(d.date))
    .y((d) => y(d.v))
    .curve(d3.curveMonotoneX)

  svg
    .append('path')
    .datum(data)
    .attr('fill', 'none')
    .style('stroke', 'var(--pink)')
    .attr('stroke-width', 3)
    .attr('d', line)

  // end marker
  const last = data[data.length - 1]
  svg
    .append('circle')
    .attr('cx', x(last.date))
    .attr('cy', y(last.v))
    .attr('r', 4)
    .style('fill', 'var(--ink)')

  // --- interactive hover: crosshair + focus dot + tooltip ---
  const focus = svg.append('g').style('display', 'none')
  focus.append('line')
    .attr('class', 'focus-line')
    .attr('y1', m.top).attr('y2', h - m.bottom)
    .style('stroke', 'var(--ink)').style('stroke-width', 1).style('stroke-dasharray', '3,3')
  focus.append('circle')
    .attr('r', 4.5)
    .style('fill', 'var(--pink)').style('stroke', 'var(--ink)').style('stroke-width', 2)
  const tip = focus.append('g')
  const tipBg = tip.append('rect')
    .attr('height', 32).attr('rx', 0)
    .style('fill', 'var(--ink)')
  const tipPrice = tip.append('text')
    .attr('x', 8).attr('y', 13)
    .style('font-family', 'var(--font-mono)').style('font-size', '11px').style('font-weight', 700)
    .style('fill', '#fff')
  const tipDate = tip.append('text')
    .attr('x', 8).attr('y', 26)
    .style('font-family', 'var(--font-mono)').style('font-size', '10px')
    .style('fill', 'var(--bg)')

  const bisect = d3.bisector((d) => d.date).center
  const fmtDate = d3.timeFormat('%b %Y')

  svg.append('rect')
    .attr('x', m.left).attr('y', m.top)
    .attr('width', Math.max(0, w - m.right - m.left))
    .attr('height', Math.max(0, h - m.bottom - m.top))
    .style('fill', 'transparent')
    .style('cursor', 'crosshair')
    .on('pointerenter pointermove', (event) => {
      const mx = d3.pointer(event)[0]
      const d = data[bisect(data, x.invert(mx))]
      if (!d) return
      focus.style('display', null)
      const px = x(d.date), py = y(d.v)
      focus.select('.focus-line').attr('x1', px).attr('x2', px)
      focus.select('circle').attr('cx', px).attr('cy', py)
      tipPrice.text('€' + Math.round(d.v).toLocaleString('en-US') + ' /m²')
      tipDate.text(fmtDate(d.date))
      const tw = Math.max(tipPrice.node().getComputedTextLength(), tipDate.node().getComputedTextLength()) + 16
      tipBg.attr('width', tw)
      // keep tooltip inside the plot
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
</style>
