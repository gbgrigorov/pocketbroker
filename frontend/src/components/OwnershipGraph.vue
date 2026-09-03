<script setup>
/*
 * Interactive D3 v7 force-directed ownership graph (Phase 3.5).
 * Nodes: builder=pink, company=blue, person=coral. Edges: ownership=teal (with
 * % label), management=grey; historical = dashed. Drag, zoom/pan, hover-highlight,
 * click a company to open its ego-network. Re-renders on data change, preserving
 * node positions by id for continuity across depth changes.
 */
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as d3 from 'd3'
import { navigate, entityPath } from '../router'
import { readLayout, writeLayout } from '../lib/graphCache'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  centerId: { type: Number, default: null },
  height: { type: Number, default: 560 },
  centerFill: { type: String, default: null }, // optional override for the centre node colour
  spacing: { type: Number, default: 1 },       // >1 spreads nodes further apart
  labelMode: { type: String, default: 'default' }, // 'default' | 'companies' | 'all'
  // Opt-in: persist the settled layout under this key so a page refresh redraws
  // an already-settled graph instead of re-running the (very expensive) settle.
  // Only worth it for the big global network; ego-networks settle in ~50ms.
  layoutKey: { type: String, default: null },
})

const host = ref(null)
const hovered = ref(null) // { name, kind, role, share, eik } for the floating tooltip
const tipXY = ref({ x: 0, y: 0 })

const FILL = { builder: 'var(--pink)', company: 'var(--blue)', person: 'var(--coral)' }
const WARN = '#FFD400' // entities carrying a public report — flagged yellow
const fillOf = (n) => (n.has_signals ? WARN : FILL[kindOf(n)])
const kindOf = (n) => (n.is_builder ? 'builder' : n.kind)
const radius = (n) => (n.id === props.centerId ? 30 : n.is_builder ? 20 : n.kind === 'person' ? 9 : 12)
// Which nodes keep a permanent label (others reveal on hover).
const HUB_MIN = 5 // a node with at least this many links is a hub worth labelling
const labelVisible = (n) => (
  props.labelMode === 'all' ? true
    // 'key' = only the important nodes: centre, builders, flagged/signal nodes,
    // and hubs (the well-connected owners) — keeps dense networks legible.
    : props.labelMode === 'key'
      ? (n.id === props.centerId || n.is_builder || n.has_signals || (degreeMap[n.id] || 0) >= HUB_MIN)
    : props.labelMode === 'companies' ? (n.is_builder || n.kind === 'company' || n.id === props.centerId)
      : (n.is_builder || n.id === props.centerId))

let svg, gZoom, sim, ro
let zoomRaf = 0, pendingTransform = null // zoom writes coalesced to one per frame
// id -> {x,y} carried across re-renders. Seeded from sessionStorage when the
// caller opted into layoutKey, so it also survives a page refresh.
const pos = props.layoutKey ? (readLayout(props.layoutKey) || {}) : {}
let degreeMap = {} // id -> incident-edge count; drives the 'key' label mode

function build() {
  const el = host.value
  if (!el) return
  const w = el.clientWidth || 800
  const h = props.height
  // Drives both the settle budget and the zoom level-of-detail below. Taken
  // from props so it is available before the node array is cloned.
  const big = props.nodes.length > 600
  // A rebuild replaces the svg; drop any queued zoom write so it can't apply a
  // stale transform to the new one.
  if (zoomRaf) { cancelAnimationFrame(zoomRaf); zoomRaf = 0 }
  d3.select(el).select('svg').remove() // keep the Vue tooltip; drop only the old svg

  svg = d3.select(el).append('svg')
    .attr('width', w).attr('height', h)
    .attr('viewBox', [0, 0, w, h])
    .style('cursor', 'grab')

  // Arrow markers (one per edge colour).
  const defs = svg.append('defs')
  for (const [id, color] of [['own', 'var(--teal)'], ['mgmt', '#8a8a8a']]) {
    defs.append('marker')
      .attr('id', `arrow-${id}`).attr('viewBox', '0 -5 10 10')
      .attr('refX', 18).attr('refY', 0).attr('markerWidth', 6).attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path').attr('class', 'arrowhead').attr('d', 'M0,-5L10,0L0,5').attr('fill', color)
  }

  gZoom = svg.append('g')
  // Touch policy: this graph lives inside scrollable pages, so one finger must
  // keep scrolling the page (touch-action: pan-y + filter). Two fingers pinch/
  // pan the graph; mouse behaviour is unchanged.
  const zoom = d3.zoom().scaleExtent([0.04, 4])
    .filter((event) => (
      event.type.startsWith('touch')
        ? (event.touches?.length ?? 0) >= 2
        : (!event.ctrlKey || event.type === 'wheel') && !event.button
    ))
    // Zoom only rewrites one transform, but the browser then re-rasterises the
    // whole subtree — on the global network that is >10k elements, so a wheel
    // gesture can outrun the frame budget badly. Two things keep it smooth:
    // coalesce the writes to one per frame (wheel/trackpad events fire far more
    // often than frames), and drop detail while zoomed out (see applyLod).
    .on('zoom', (e) => {
      pendingTransform = e.transform
      if (zoomRaf) return
      zoomRaf = requestAnimationFrame(() => {
        zoomRaf = 0
        gZoom.attr('transform', pendingTransform)
        applyLod(pendingTransform.k)
      })
    })
  svg.call(zoom)
  svg.style('touch-action', 'pan-y')

  // Level of detail. What makes zooming choppy is the number of *painted*
  // things, not the transform: every edge draws an arrowhead marker (a nested
  // render subtree per use) and every label is stroked via paint-order, which
  // paints the glyphs twice. Below this scale none of that detail is legible
  // anyway, so it is switched off with a single class on the root — one DOM
  // write per threshold crossing rather than thousands of attribute writes.
  const LOD_MIN_K = 0.5
  let lod = null
  function applyLod(k) {
    const next = big && k < LOD_MIN_K ? 'lite' : 'full'
    if (next === lod) return
    lod = next
    svg.classed('lod-lite', next === 'lite')
  }

  // Clone data (D3 mutates) and seed positions from the previous layout.
  const nodes = props.nodes.map((n) => ({ ...n, ...(pos[n.id] || {}) }))
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const links = props.edges
    .filter((e) => byId.has(e.source) && byId.has(e.target))
    .map((e) => ({ ...e }))

  // Edge counts per node (raw ids, before the sim rewrites source/target into
  // node refs) — the 'key' label mode keeps labels only on hubs.
  degreeMap = {}
  links.forEach((l) => {
    degreeMap[l.source] = (degreeMap[l.source] || 0) + 1
    degreeMap[l.target] = (degreeMap[l.target] || 0) + 1
  })

  const link = gZoom.append('g').attr('class', 'links').selectAll('line')
    .data(links).join('line')
    .attr('stroke', (d) => (d.relation === 'ownership' ? 'var(--teal)' : '#8a8a8a'))
    .attr('stroke-width', (d) => (d.relation === 'ownership' ? 2.5 : 1.5))
    .attr('stroke-dasharray', (d) => (d.is_current ? null : '5,4'))
    .attr('marker-end', (d) => `url(#arrow-${d.relation === 'ownership' ? 'own' : 'mgmt'})`)

  const elabel = gZoom.append('g').attr('class', 'elabels').selectAll('text')
    .data(links.filter((d) => d.share_pct != null)).join('text')
    .text((d) => `${Math.round(d.share_pct)}%`)
    .attr('font-family', 'var(--font-mono)').attr('font-size', 10)
    .attr('fill', 'var(--ink)').attr('text-anchor', 'middle')
    .attr('paint-order', 'stroke').attr('stroke', 'var(--bg)').attr('stroke-width', 3)

  const node = gZoom.append('g').attr('class', 'nodes').selectAll('g')
    .data(nodes).join('g')
    .attr('class', 'node')
    .style('cursor', (d) => (d.key ? 'pointer' : 'default'))
    .call(d3.drag()
      // No node-dragging with a finger — it would also swallow page scroll.
      .filter((event) => event.type !== 'touchstart' && !event.ctrlKey && !event.button)
      .on('start', (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y })
      .on('end', (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null }))
    .on('click', (_e, d) => { if (d.key) navigate(entityPath(d.key, d.slug)) })
    .on('mouseenter', (e, d) => { hovered.value = { name: d.name, kind: kindOf(d), eik: d.eik }; focus(d) })
    .on('mousemove', (e) => { const r = host.value.getBoundingClientRect(); tipXY.value = { x: e.clientX - r.left, y: e.clientY - r.top } })
    .on('mouseleave', () => { hovered.value = null; focus(null) })

  node.append('circle')
    .attr('r', radius)
    .attr('fill', (d) => (d.id === props.centerId && props.centerFill ? props.centerFill : fillOf(d)))
    .attr('stroke', 'var(--ink)')
    .attr('stroke-width', (d) => (d.id === props.centerId ? 3.5 : 2))

  // Labels: always for builders + the centre; others reveal on hover.
  node.append('text')
    .attr('class', 'nlabel')
    .text((d) => (d.name?.length > 22 ? d.name.slice(0, 21) + '…' : d.name))
    .attr('text-anchor', 'middle')
    .attr('dy', (d) => radius(d) + 13)
    .attr('font-family', 'var(--font-display)').attr('font-weight', 800)
    .attr('font-size', (d) => (d.id === props.centerId ? 14 : 11))
    .style('text-transform', 'uppercase')
    .attr('fill', 'var(--ink)')
    .attr('paint-order', 'stroke').attr('stroke', 'var(--bg)').attr('stroke-width', 3)
    // display, not opacity: a fully transparent <text> is still laid out and
    // painted (and these are stroked, so painted twice). On the global network
    // that is ~1800 hidden labels costing full paint time on every zoom frame.
    .style('display', (d) => (labelVisible(d) ? null : 'none'))
    .style('pointer-events', 'none')

  const adj = new Map() // id -> Set(neighbour ids) for hover focus
  links.forEach((l) => {
    const s = l.source.id ?? l.source, t = l.target.id ?? l.target
    ;(adj.get(s) || adj.set(s, new Set()).get(s)).add(t)
    ;(adj.get(t) || adj.set(t, new Set()).get(t)).add(s)
  })

  function focus(d) {
    if (!d) {
      node.style('opacity', 1)
      link.style('opacity', 1)
      node.select('.nlabel').style('display', (n) => (labelVisible(n) ? null : 'none'))
      return
    }
    const keep = adj.get(d.id) || new Set()
    node.style('opacity', (n) => (n.id === d.id || keep.has(n.id) ? 1 : 0.12))
    node.select('.nlabel').style('display', (n) => (n.id === d.id || keep.has(n.id) ? null : 'none'))
    link.style('opacity', (l) => {
      const s = l.source.id ?? l.source, t = l.target.id ?? l.target
      return s === d.id || t === d.id ? 1 : 0.06
    })
  }

  function ticked() {
    link.attr('x1', (d) => d.source.x).attr('y1', (d) => d.source.y)
      .attr('x2', (d) => d.target.x).attr('y2', (d) => d.target.y)
    elabel.attr('x', (d) => (d.source.x + d.target.x) / 2)
      .attr('y', (d) => (d.source.y + d.target.y) / 2)
    node.attr('transform', (d) => `translate(${d.x},${d.y})`)
  }

  function fit() {
    if (!nodes.length) return
    const xs = nodes.map((n) => n.x), ys = nodes.map((n) => n.y)
    const minX = Math.min(...xs), maxX = Math.max(...xs)
    const minY = Math.min(...ys), maxY = Math.max(...ys)
    const gw = maxX - minX || 1, gh = maxY - minY || 1
    const scale = Math.min(w / gw, h / gh, 1.4) * 0.88
    // Settle the detail level before the first paint. A 2000-node graph fits at
    // a small scale, so this avoids painting full detail for one frame and then
    // immediately throwing it away when the transition starts firing zoom events.
    applyLod(scale)
    const tx = w / 2 - scale * (minX + maxX) / 2
    const ty = h / 2 - scale * (minY + maxY) / 2
    svg.transition().duration(450).call(zoom.transform,
      d3.zoomIdentity.translate(tx, ty).scale(scale))
  }

  // Pre-settle synchronously (avoids the off-screen "fly-in"), render once, fit.
  //
  // This is the single most expensive thing on the page: the per-tick cost grows
  // with node count, so on the 2000-node global network a full 400-tick settle
  // blocks the main thread for ~8s. Three things keep it cheap:
  //   - if every node came in with a cached position the graph is already
  //     settled, so it needs no ticks at all (~8s -> ~5ms on refresh);
  //   - big graphs cool on a shorter schedule — fewer ticks, but alphaDecay is
  //     retuned so the simulation still reaches alphaMin instead of being cut
  //     off mid-motion, which is what actually makes a layout look unfinished;
  //   - big graphs also use a coarser Barnes-Hut theta, which roughly halves
  //     the charge force's cost and is visually indistinguishable at this size.
  // Must be decided BEFORE forceSimulation(), which seeds x/y on every node that
  // lacks them — after that call "has coordinates" is true even for a cold graph.
  const restored = nodes.length > 0 && nodes.every((n) => Number.isFinite(n.x) && Number.isFinite(n.y))
  const ticks = restored
    ? (big ? 0 : 30) // already settled; small graphs get a cheap touch-up
    : Math.min(big ? 150 : 400, 120 + nodes.length)

  const charge = d3.forceManyBody().strength((nodes.length > 200 ? -120 : -300) * props.spacing)
  if (big) charge.theta(1.5)
  sim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id((d) => d.id).distance(70 * props.spacing).strength(0.6))
    .force('charge', charge)
    .force('center', d3.forceCenter(w / 2, h / 2))
    .force('collide', d3.forceCollide((d) => radius(d) + 6 * props.spacing))
    .stop()
  if (ticks > 0) {
    sim.alphaDecay(1 - Math.pow(sim.alphaMin(), 1 / ticks))
    sim.tick(ticks)
  }

  nodes.forEach((n) => { pos[n.id] = { x: n.x, y: n.y } })
  // Only persist when we actually settled something. A resize re-runs build()
  // with the layout already restored (0 ticks) — rewriting ~100KB of unchanged
  // coordinates on every ResizeObserver callback would just add jank.
  if (props.layoutKey && ticks > 0) writeLayout(props.layoutKey, pos)
  ticked()
  fit()
  sim.on('tick', ticked) // resumes on drag (alphaTarget restart)
}

onMounted(() => {
  build()
  ro = new ResizeObserver(() => { if (sim) sim.stop(); build() })
  ro.observe(host.value)
})
onBeforeUnmount(() => {
  ro?.disconnect()
  sim?.stop()
  if (zoomRaf) { cancelAnimationFrame(zoomRaf); zoomRaf = 0 }
})
watch(() => [props.nodes, props.edges, props.centerId], () => { if (sim) sim.stop(); build() })
</script>

<template>
  <div class="graph" ref="host" :style="{ height: height + 'px' }">
    <div v-if="hovered" class="tip" :style="{ left: tipXY.x + 14 + 'px', top: tipXY.y + 14 + 'px' }">
      <span class="dot" :class="hovered.kind"></span>
      <span class="tip__name">{{ hovered.name }}</span>
      <span v-if="hovered.eik" class="tip__eik mono">ЕИК {{ hovered.eik }}</span>
    </div>
  </div>
</template>

<style scoped>
.graph {
  position: relative;
  width: 100%;
  background: var(--bg);
  border: var(--stroke);
  box-shadow: var(--shadow);
  overflow: hidden;
}
/* Edges and edge labels carry no interaction — taking them out of hit-testing
   keeps pointer moves off the 3.5k-element link layer while panning. */
.graph :deep(.links),
.graph :deep(.elabels) { pointer-events: none; }

/* Zoomed-out detail level (see applyLod). Arrowheads and share labels are
   sub-pixel at this scale but still cost full paint time on every frame. */
.graph :deep(svg.lod-lite .elabels) { display: none; }
.graph :deep(svg.lod-lite .arrowhead) { display: none; }
.tip {
  position: absolute;
  pointer-events: none;
  background: var(--surface);
  border: var(--stroke);
  box-shadow: var(--shadow);
  padding: 6px 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 280px;
  z-index: 5;
}
.tip__name { font-family: var(--font-display); font-weight: 800; text-transform: uppercase; font-size: 14px; }
.tip__eik { font-size: 11px; color: #555; }
.dot { width: 12px; height: 12px; border: 2px solid var(--ink); flex: none; border-radius: 50%; }
.dot.builder { background: var(--pink); }
.dot.company { background: var(--blue); }
.dot.person { background: var(--coral); }
</style>
