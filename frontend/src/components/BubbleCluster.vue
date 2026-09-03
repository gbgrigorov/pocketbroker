<script setup>
/*
 * Shared force-bubble cluster. One <circle> per node, sized by `value`, filled by
 * `color`. Two layouts:
 *   - directional : a fixed centre bubble + compass-anchored satellites (deep-dive ring)
 *   - pack        : all bubbles pulled gently to the middle, collision-packed (home field)
 * Node shape: { slug, name, value, label, color, isCenter?, direction? }
 * Clicking a non-centre bubble dives into that neighbourhood.
 */
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as d3 from 'd3'
import { navigate } from '../router'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  mode: { type: String, default: 'pack' }, // 'pack' | 'directional'
  height: { type: Number, default: null }, // null = fill container height
  radiusRange: { type: Array, default: null },
  // Hash path prefix a bubble click navigates to: `${linkPrefix}/${slug}`.
  linkPrefix: { type: String, default: '/n' },
  // Scroll/pinch/drag zoom + pan. Disable for static rings (e.g. deep-dive).
  zoomable: { type: Boolean, default: true },
})

const el = ref(null)

const DIR = {
  N: [0, -1], NE: [0.71, -0.71], E: [1, 0], SE: [0.71, 0.71],
  S: [0, 1], SW: [-0.71, 0.71], W: [-1, 0], NW: [-0.71, -0.71],
}
const NULL_R = 7

let svg = null
let gWrap = null
let zoom = null
let curTransform = d3.zoomIdentity // persisted so zoom survives metric/year re-renders
let ro = null
let curW = 0
let curH = 0
const prevPos = {} // slug -> {x,y} carried across updates for continuity

// Reuse the existing <svg> across re-renders (e.g. slider ticks) so the D3
// data-join can TWEEN radii/positions. Only rebuild when the canvas resizes —
// otherwise bubbles would be destroyed and re-created from r=0 (a jarring pop).
function ensureSvg(host, w, h) {
  if (svg && curW === w && curH === h) return
  host.innerHTML = ''
  curW = w
  curH = h
  svg = d3.select(host).append('svg').attr('width', w).attr('height', h)
  gWrap = svg.append('g')
  // Pan + scroll/pinch zoom: the wheel scales, drag pans. The transform lives
  // on gWrap so the per-node translates inside it compose cleanly underneath.
  if (props.zoomable) {
    zoom = d3.zoom()
      .scaleExtent([0.6, 8])
      .on('zoom', (e) => {
        gWrap.attr('transform', e.transform)
        curTransform = e.transform
        scaleLabels()
      })
      .on('end', refitLabels)
    svg.call(zoom)
    // Let d3 own all touch gestures: one-finger pan + two-finger pinch. Safe
    // because every zoomable canvas is fixed-height, so there is no page
    // scroll to fight with.
    svg.style('touch-action', 'none')
    svg.call(zoom.transform, curTransform) // restore after a resize-driven rebuild
  }
}

function zoomIn() { if (svg && zoom) svg.transition().duration(200).call(zoom.scaleBy, 1.4) }
function zoomOut() { if (svg && zoom) svg.transition().duration(200).call(zoom.scaleBy, 1 / 1.4) }
function resetZoom() { if (svg && zoom) svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity) }
defineExpose({ zoomIn, zoomOut, resetZoom })

function render() {
  const host = el.value
  if (!host) return
  const w = host.clientWidth || 520
  const h = props.height || host.clientHeight || 380
  if (w === 0 || h === 0) return
  const cx = w / 2
  const cy = h / 2
  ensureSvg(host, w, h)

  // Pack min radius is generous so even the smallest bubble can host a short,
  // legible (truncated) name rather than overflowing it.
  const range = props.radiusRange || (props.mode === 'directional' ? [26, 64] : [18, 52])
  const vals = props.nodes.map((n) => n.value).filter((v) => v != null)
  const maxV = d3.max(vals) || 1
  const minV = d3.min(vals) || 0
  const r = d3.scaleSqrt().domain([Math.min(minV, maxV * 0.4), maxV]).range(range).clamp(true)
  const radOf = (n) => (n.value != null ? r(n.value) : NULL_R)
  const ring = Math.min(w, h) / 2 - Math.max(70, range[1] + 10)

  // Geo projection for pack mode: map lat/lon → screen so each bubble's force
  // anchor sits at its true relative position (north up, west left). Uniform,
  // aspect-correct scale (lon compressed by cos(lat)) keeps compass directions
  // faithful; collision then packs the bubbles snugly without overlap.
  const geoOf = buildGeoProjection(props.nodes, w, h, range[1] + 16)
  const packAnchor = props.mode === 'pack'
    ? buildPackAnchors(props.nodes, geoOf, radOf, cx, cy)
    : null

  const nodes = props.nodes.map((n) => {
    const seed = prevPos[n.slug]
    if (props.mode === 'directional' && n.isCenter) {
      return { ...n, rad: radOf(n), fx: cx, fy: cy, x: cx, y: cy }
    }
    if (props.mode === 'directional') {
      const [dx, dy] = DIR[n.direction] || [0, 0]
      return {
        ...n, rad: radOf(n), ax: cx + dx * ring, ay: cy + dy * ring,
        x: seed ? seed.x : cx + dx * ring, y: seed ? seed.y : cy + dy * ring,
      }
    }
    // pack: anchor each bubble at its (outlier-corrected) geographic position
    const a = packAnchor(n.slug)
    return {
      ...n, rad: a.rad, ax: a.ax, ay: a.ay,
      x: seed ? seed.x : a.ax, y: seed ? seed.y : a.ay,
    }
  })

  const xStrength = props.mode === 'directional' ? 0.5 : 0.22
  const sim = d3.forceSimulation(nodes)
    .force('x', d3.forceX((d) => (d.isCenter ? cx : d.ax)).strength(xStrength))
    .force('y', d3.forceY((d) => (d.isCenter ? cy : d.ay)).strength(xStrength))
    .force('collide', d3.forceCollide((d) => d.rad + 3).strength(1))
    .stop()
  for (let i = 0; i < 260; i++) sim.tick()
  nodes.forEach((n) => { prevPos[n.slug] = { x: n.x, y: n.y } })

  const T = d3.transition().duration(500).ease(d3.easeCubicOut)
  const g = gWrap.selectAll('g.node').data(nodes, (d) => d.slug)

  const gEnter = g.enter().append('g')
    .attr('class', 'node')
    .attr('transform', (d) => `translate(${d.x},${d.y})`)
    .style('cursor', (d) => (d.slug && !d.isCenter ? 'pointer' : 'default'))
    .on('click', (_e, d) => { if (d.slug && !d.isCenter) navigate(`${props.linkPrefix}/${d.slug}`) })
  gEnter.append('title')
  gEnter.append('circle').attr('stroke', 'var(--ink)').attr('stroke-width', 2)
  gEnter.append('text').attr('class', 'nm')
    .attr('text-anchor', 'middle').attr('dy', '-0.1em')
    .style('font-family', 'var(--font-display)').style('font-weight', 800)
    .style('text-transform', 'uppercase').style('fill', '#fff').style('pointer-events', 'none')
  gEnter.append('text').attr('class', 'vl')
    .attr('text-anchor', 'middle').attr('dy', '1.15em')
    .style('font-family', 'var(--font-mono)').style('font-size', '10px')
    .style('fill', '#fff').style('pointer-events', 'none')

  const gAll = gEnter.merge(g)
  gAll.transition(T).attr('transform', (d) => `translate(${d.x},${d.y})`)
  gAll.select('title').text((d) => `${d.name}${d.label ? ' · ' + d.label : ''}`)
  gAll.select('circle').transition(T)
    .attr('r', (d) => d.rad)
    .attr('fill', (d) => d.color || 'var(--neutral)')
  // Show the value line only when the bubble is tall enough for two lines;
  // otherwise the name is vertically centred and gets the whole circle.
  const showVal = (d) => d.rad >= 21
  // Font scales across the full radius range so the smallest bubbles get a
  // genuinely smaller font, not just a clamped floor. Bounds differ per mode.
  const fb = props.mode === 'directional'
    ? { nLo: 11, nHi: 15, vLo: 9, vHi: 12 }
    : { nLo: 7, nHi: 14, vLo: 6, vHi: 11 }
  const lerpFont = (rad, lo, hi) =>
    clamp(lo + ((rad - range[0]) / (range[1] - range[0] || 1)) * (hi - lo), lo, hi)
  gAll.select('text.nm')
    .style('font-size', (d) => (d.isCenter ? fb.nHi : lerpFont(d.rad, fb.nLo, fb.nHi)) + 'px')
    .attr('dy', (d) => (showVal(d) ? '-0.1em' : '0.32em'))
    .style('fill', (d) => (textColor(d)))
    .style('opacity', 1)
    .each(function (d) { fitLabel(this, d.name, d.rad * 2 - 8) })
  gAll.select('text.vl')
    .style('font-size', (d) => lerpFont(d.rad, fb.vLo, fb.vHi) + 'px')
    .style('fill', (d) => textColor(d))
    .style('opacity', (d) => (showVal(d) ? 1 : 0))
    .text((d) => d.label || '')

  g.exit().remove()

  // A pinch zoom may be live (curTransform persists) — re-apply it to the
  // freshly joined labels.
  scaleLabels()
  refitLabels()
}

// Keep label legible on the rare light fill (e.g. the PtR "fair" yellow).
function textColor(d) {
  return d.color === '#ffd34d' ? 'var(--ink)' : '#fff'
}

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v))

/*
 * Zoom-adaptive labels. Text scales with sqrt(zoom) instead of linearly, so as
 * you zoom in the circles outgrow their labels and the freed-up width lets
 * longer (un-truncated) names + hidden value lines appear — this is what makes
 * the zoomed-out mobile field legible after a pinch.
 */
function scaleLabels() {
  if (!gWrap) return
  const k = curTransform.k
  const s = k > 1 ? 1 / Math.sqrt(k) : 1 // counter-scale: net text growth = sqrt(k)
  gWrap.selectAll('g.node text').attr('transform', s === 1 ? null : `scale(${s})`)
}

function refitLabels() {
  if (!gWrap) return
  const grow = Math.max(1, Math.sqrt(curTransform.k)) // extra label width earned by zooming
  gWrap.selectAll('g.node').each(function (d) {
    const g = d3.select(this)
    const showVal = d.rad * grow >= 21
    g.select('text.nm')
      .attr('dy', showVal ? '-0.1em' : '0.32em')
      .each(function () { fitLabel(this, d.name, (d.rad * 2 - 8) * grow) })
    g.select('text.vl').style('opacity', showVal ? 1 : 0)
  })
}

// Set the bubble's name, trimming with an ellipsis until it fits inside the
// circle width. Measures the real rendered text (font-size is already applied),
// so it adapts to bubble size and font without hard character limits.
function fitLabel(node, full, maxW) {
  node.textContent = full
  if (node.getComputedTextLength() <= maxW) return
  let s = full
  while (s.length > 1) {
    s = s.slice(0, -1)
    node.textContent = s + '…'
    if (node.getComputedTextLength() <= maxW) return
  }
}

// Build a lat/lon → [x,y] projector that fits all geo-located nodes into the
// canvas with a single uniform scale (so a degree east and a degree north map to
// the same pixel distance, after correcting lon for latitude). North is up.
// Returns a function; nodes without coords get null so callers can fall back.
function buildGeoProjection(nodes, w, h, pad) {
  const pts = nodes.filter((n) => n.lat != null && n.lon != null)
  if (pts.length < 2) return () => null
  const meanLat = d3.mean(pts, (n) => n.lat)
  const k = Math.cos((meanLat * Math.PI) / 180) // lon compression at this latitude
  const rx = (n) => n.lon * k
  const ry = (n) => -n.lat // invert so north (higher lat) is up
  const minX = d3.min(pts, rx), maxX = d3.max(pts, rx)
  const minY = d3.min(pts, ry), maxY = d3.max(pts, ry)
  const spanX = maxX - minX || 1
  const spanY = maxY - minY || 1
  const scale = Math.min((w - 2 * pad) / spanX, (h - 2 * pad) / spanY)
  // Centre the (uniformly scaled) bounding box within the canvas.
  const offX = (w - spanX * scale) / 2
  const offY = (h - spanY * scale) / 2
  return (n) => {
    if (n.lat == null || n.lon == null) return null
    return [offX + (rx(n) - minX) * scale, offY + (ry(n) - minY) * scale]
  }
}

// Resolve a final anchor per bubble for pack mode. Starts from the geo
// projection, then snaps geographic outliers inward: any bubble whose nearest
// neighbour is more than GAP_MAX px away is re-anchored to just touch that
// neighbour, on the same side — so it stays in its true compass direction
// instead of floating alone in empty canvas (e.g. Изток, 5km from anything).
function buildPackAnchors(nodes, geoOf, radOf, cx, cy) {
  const GAP_MAX = 26 // px of empty space before a bubble counts as an outlier
  const a = nodes.map((n) => {
    const p = geoOf(n) || [cx, cy]
    return { slug: n.slug, rad: radOf(n), ax: p[0], ay: p[1] }
  })
  for (let pass = 0; pass < 4; pass++) {
    let moved = false
    for (const node of a) {
      let near = null, nd = Infinity
      for (const other of a) {
        if (other === node) continue
        const d = Math.hypot(node.ax - other.ax, node.ay - other.ay)
        if (d < nd) { nd = d; near = other }
      }
      if (!near || nd === 0) continue
      if (nd - node.rad - near.rad > GAP_MAX) {
        const ux = (node.ax - near.ax) / nd, uy = (node.ay - near.ay) / nd
        const reach = node.rad + near.rad + 4 // small overlap → collision seats it touching
        node.ax = near.ax + ux * reach
        node.ay = near.ay + uy * reach
        moved = true
      }
    }
    if (!moved) break
  }
  const byslug = {}
  a.forEach((x) => { byslug[x.slug] = x })
  return (slug) => byslug[slug] || { rad: 7, ax: cx, ay: cy }
}

onMounted(() => {
  render()
  ro = new ResizeObserver(() => render())
  ro.observe(el.value)
})
onBeforeUnmount(() => ro?.disconnect())
watch(() => [props.nodes, props.mode, props.height], render, { deep: true })
</script>

<template>
  <div ref="el" class="cluster" :style="height ? { height: height + 'px' } : null"></div>
</template>

<style scoped>
.cluster { width: 100%; height: 100%; }
.cluster :deep(svg) { cursor: grab; }
.cluster :deep(svg:active) { cursor: grabbing; }
.cluster :deep(circle) { transition: filter 0.2s; }
.cluster :deep(g.node:hover circle) { filter: brightness(0.92); }
</style>
