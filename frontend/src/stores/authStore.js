import { defineStore } from 'pinia'
import { api, TOKEN_KEY } from '../api'
import { clearGraphCache } from '../lib/graphCache'

// Login state. The JWT is persisted to localStorage so a refresh keeps you signed
// in; the api client reads it from there to attach the Authorization header.
export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || null,
    user: null,
    error: null,
    modalOpen: false, // the AuthModal (login/register) — opened from the sidebar / lock CTAs
    // False until the initial fetchMe() settles. App.vue kicks that off without
    // awaiting it, so on a hard refresh a view can mount while `user` is still
    // null — indistinguishable from "signed out" unless you check this flag.
    ready: false,
  }),
  getters: {
    isAuthenticated: (s) => !!s.token,
    displayName: (s) => s.user?.name || s.user?.email || '',
  },
  actions: {
    setToken(token) {
      this.token = token
      if (token) localStorage.setItem(TOKEN_KEY, token)
      else localStorage.removeItem(TOKEN_KEY)
      // The cached ownership graph is login-gated people data. Drop it on every
      // token change — login, logout, or a token the server rejected — so it can
      // never outlive the session that was entitled to it.
      clearGraphCache()
    },
    async login(email, password) {
      this.error = null
      this.setToken(await api.login(email, password))
      await this.fetchMe()
    },
    async register(email, password, name) {
      this.error = null
      await api.register(email, password, name)
      await this.login(email, password)
    },
    // Send the browser to Google; it returns to /auth?token=… (see App.vue onMounted).
    async startGoogle() {
      window.location.href = await api.googleAuthorizeUrl()
    },
    async fetchMe() {
      if (!this.token) {
        this.ready = true // anonymous, but resolved
        return
      }
      try {
        this.user = await api.me()
      } catch (e) {
        this.setToken(null) // token rejected → fall back to anonymous
        this.user = null
      } finally {
        this.ready = true
      }
    },
    logout() {
      this.setToken(null)
      this.user = null
    },
    openModal() { this.error = null; this.modalOpen = true },
    closeModal() { this.modalOpen = false },
  },
})
