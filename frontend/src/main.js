import { createApp } from 'vue'
import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import 'leaflet/dist/leaflet.css'
import './styles/tokens.css'
import './styles/global.css'
import App from './App.vue'
import i18n from './i18n'

createApp(App)
  .use(createPinia())
  .use(i18n)
  .use(PrimeVue, { unstyled: true })
  .mount('#app')
