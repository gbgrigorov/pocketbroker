// Bulgaria silhouette + a shared lon/lat → x/y projection.
//
// One equirectangular projection (lon→x, lat→y flipped, lon compressed by
// cos(meanLat) so the country isn't horizontally stretched) drives BOTH the
// outline path and the city pins — so a pin placed from its centroid always
// lands inside the border by construction.
//
// BORDER is a heavily simplified Bulgaria boundary ring (public-domain shape,
// Natural Earth admin-0, hand-simplified) — embedded so there's no runtime
// network call and nothing to install. It's a stylised silhouette for the
// Neo-Memphis home map, not a survey-grade boundary.

// [lon, lat] going clockwise from the north-west (Danube/Timok) corner.
const BORDER = [
  [22.66, 44.17], [22.95, 43.99], [23.6, 43.79], [24.5, 43.7], [25.35, 43.62],
  [26.2, 44.0], [27.0, 44.13], [27.27, 44.12], [28.02, 43.74], [28.58, 43.74],
  [28.2, 43.4], [27.95, 43.19], [27.83, 42.92], [27.9, 42.69], [27.46, 42.46],
  [27.62, 42.18], [28.02, 41.98], [27.55, 42.0], [26.96, 42.0], [26.36, 41.71],
  [26.13, 41.36], [25.55, 41.31], [25.28, 41.24], [24.8, 41.4], [24.5, 41.57],
  [24.06, 41.46], [23.6, 41.38], [23.21, 41.38], [22.95, 41.34], [22.88, 41.75],
  [22.36, 42.32], [22.5, 42.74], [22.45, 43.0], [22.6, 43.39], [22.4, 43.74],
  [22.55, 44.0], [22.66, 44.17],
]

export const VIEW_W = 1000
const PAD = 28
const MEAN_LAT = 42.7
const K = Math.cos((MEAN_LAT * Math.PI) / 180) // lon compression at this latitude

// Raw equirectangular coords (north up). Compute the bounding box once.
const rx = (lon) => lon * K
const ry = (lat) => -lat
const xs = BORDER.map(([lon]) => rx(lon))
const ys = BORDER.map(([, lat]) => ry(lat))
const minX = Math.min(...xs)
const maxX = Math.max(...xs)
const minY = Math.min(...ys)
const maxY = Math.max(...ys)
const spanX = maxX - minX || 1
const spanY = maxY - minY || 1

const SCALE = (VIEW_W - 2 * PAD) / spanX
export const VIEW_H = Math.round(spanY * SCALE + 2 * PAD)

/** lon/lat → { x, y } in the SVG's viewBox coordinate space. */
export function project(lon, lat) {
  return {
    x: PAD + (rx(lon) - minX) * SCALE,
    y: PAD + (ry(lat) - minY) * SCALE,
  }
}

export const VIEW_BOX = `0 0 ${VIEW_W} ${VIEW_H}`

export const OUTLINE_PATH =
  'M' +
  BORDER.map(([lon, lat]) => {
    const { x, y } = project(lon, lat)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join('L') +
  'Z'
