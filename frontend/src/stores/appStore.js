import { defineStore } from 'pinia'
import { api } from '../api'
import { METRICS, AIR_METRICS, rankFeatures } from '../lib/metrics'
import { isExtended } from '../lib/scope'

export const useAppStore = defineStore('app', {
  state: () => ({
    cities: [], // [{ slug, name, lat, lon, neighbourhood_count, avg_eur_sqm }] — for the country map
    city: null, // active city slug (set when a city's bubble field is open)
    // All-years payload for the active city, fetched once:
    // [{ slug, name, lat, lon, latest:{sale,rent}, by_year:{ "2025":{sale,rent}, … } }]
    rawFeatures: [],
    year: null, // null = latest
    metric: 'price', // which signal drives bubble size + colour
    season: 'winter', // 'winter' (Jan) | 'summer' (Jul) — only affects the air metrics
    scope: 'sofia', // 'sofia' = city only | 'extended' = + villages/towns (Sofia only)
    activeSlug: null,
    loading: false,
    error: null,
  }),
  getters: {
    metricDef: (s) => METRICS[s.metric] || METRICS.price,
    // Air-data year coverage per season, derived from the loaded features. Drives
    // the air-mode slider so its range is EXACTLY the years we have for the active
    // season (and auto-grows as new years are crawled) instead of the 1995–2026
    // price span. Seasonal because coverage differs (today: winter 2018–2026,
    // summer 2017–2025). Empty arrays until a city with air data is loaded.
    airYears(s) {
      const seasons = { winter: new Set(), summer: new Set() }
      for (const f of s.rawFeatures) {
        if (!f.air) continue
        for (const [y, cell] of Object.entries(f.air)) {
          if (cell?.winter) seasons.winter.add(Number(y))
          if (cell?.summer) seasons.summer.add(Number(y))
        }
      }
      return {
        winter: [...seasons.winter].sort((a, b) => a - b),
        summer: [...seasons.summer].sort((a, b) => a - b),
      }
    },
    // Display name of the active city (from the loaded list, else its slug).
    cityName(s) {
      const c = s.cities.find((c) => c.slug === s.city)
      return c?.name || (s.city ? s.city[0].toUpperCase() + s.city.slice(1) : '')
    },
    // Project the all-years payload down to the active year (or `latest` when
    // year is null). A year with no priced data for a feature yields nulls — the
    // metrics/bubble code already renders those as a placeholder, not a crash.
    // This is what the slider drives: changing `year` re-derives this locally,
    // no refetch. Shape matches the old /map response so downstream is unchanged.
    featuresForYear() {
      const key = this.year == null ? null : String(this.year)
      return this.rawFeatures.map((f) => {
        const cell = key == null ? f.latest : f.by_year?.[key]
        const sale = cell?.sale ?? null
        const rent = cell?.rent ?? null
        // Air is seasonal: f.air[year][season] = { pm25, aqi, n }. Air coverage is
        // sparser than prices, so fall back to the nearest available air year (and
        // for "Latest" use the most recent) — keeps the air bubbles from vanishing
        // on years we don't yet have, instead of looking like a dead slider.
        // Crucially the fallback is per-SEASON: coverage differs by season (e.g.
        // 2026 has winter but no summer yet), so we only consider years that hold
        // data for the selected season. A season-blind pick would land on a year
        // whose season is empty and silently drop the bubble.
        let airCell = null
        if (f.air) {
          const seasonYears = Object.keys(f.air).filter((y) => f.air[y]?.[this.season])
          if (seasonYears.length) {
            const target = key != null ? Number(key) : Infinity
            const airKey =
              key != null && f.air[key]?.[this.season]
                ? key
                : seasonYears.reduce((best, y) =>
                    Math.abs(Number(y) - target) < Math.abs(Number(best) - target) ? y : best
                  )
            airCell = f.air[airKey][this.season]
          }
        }
        return {
          slug: f.slug, name: f.name, lat: f.lat, lon: f.lon,
          value: sale, sale_eur_sqm: sale, rent_eur_sqm: rent,
          pm25: airCell?.pm25 ?? null,
          aqi: airCell?.aqi ?? null,
          air_n: airCell?.n ?? null,
        }
      })
    },
    // Features within the active city scope. The Sofia/extended split (villages,
    // annexed towns) only applies to Sofia; other cities show all their features.
    scopedFeatures() {
      if (this.city === 'sofia' && this.scope === 'sofia') {
        return this.featuresForYear.filter((f) => !isExtended(f.slug))
      }
      return this.featuresForYear
    },
    // Sidebar ranking for the active metric: [{ slug, name, text }]
    ranked() {
      return rankFeatures(this.scopedFeatures, this.metric)
    },
  },
  actions: {
    async loadCities() {
      if (this.cities.length) return // country pins are static — fetch once
      this.loading = true
      this.error = null
      try {
        this.cities = await api.cities()
      } catch (e) {
        this.error = String(e)
      } finally {
        this.loading = false
      }
    },
    // Load the bubble field for one city — all years at once. Cached: re-opening
    // the same city is a no-op, and the year slider never refetches (see setYear).
    async loadCity(citySlug) {
      if (this.city === citySlug && this.rawFeatures.length) return
      this.city = citySlug
      this.loading = true
      this.error = null
      try {
        this.rawFeatures = await api.map(citySlug)
      } catch (e) {
        this.error = String(e)
      } finally {
        this.loading = false
      }
    },
    // Year switch is now a pure client-side filter (featuresForYear) — no fetch.
    setYear(year) {
      this.year = year
    },
    setSeason(season) {
      if (season === 'winter' || season === 'summer') this.season = season
    },
    setMetric(metric) {
      if (METRICS[metric]) this.metric = metric
    },
    // Keep the active metric in the family the URL section demands. Only fires
    // when the metric is in the wrong family, so a sub-metric choice within a
    // section (price↔PtR, AQI↔PM2.5) is preserved across navigation.
    applySection(section) {
      const air = AIR_METRICS.includes(this.metric)
      if (section === 'air' && !air) this.metric = 'pm25'
      if (section === 'estate' && air) this.metric = 'price'
    },
    setScope(scope) {
      if (scope === 'sofia' || scope === 'extended') this.scope = scope
    },
    select(slug) {
      this.activeSlug = slug
    },
  },
})
