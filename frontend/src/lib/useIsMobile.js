// Reactive "phone-sized viewport" flag, shared by views that swap layouts
// (e.g. CityView renders BubbleFlow instead of the zoomable BubbleCluster).
// Keep the query in sync with the CSS breakpoint used across components.
import { ref, onMounted, onBeforeUnmount } from 'vue'

const QUERY = '(max-width: 768px)'

export function useIsMobile() {
  const mql = window.matchMedia(QUERY)
  const isMobile = ref(mql.matches)
  const onChange = (e) => { isMobile.value = e.matches }
  onMounted(() => mql.addEventListener('change', onChange))
  onBeforeUnmount(() => mql.removeEventListener('change', onChange))
  return isMobile
}
