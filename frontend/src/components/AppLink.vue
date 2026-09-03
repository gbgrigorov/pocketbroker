<script setup>
// Drop-in replacement for `<a href="#/..." @click.prevent="navigate(...)">`.
// Renders a real, crawlable <a href> (clean History-mode path) while still
// doing client-side navigation on a plain left-click. Modifier-clicks (new
// tab/window) and middle-clicks fall through to native <a> behaviour.
import { navigate } from '../router'

const props = defineProps({ to: { type: String, required: true } })

function onClick(e) {
  if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
  e.preventDefault()
  navigate(props.to)
}
</script>

<template>
  <a :href="to" @click="onClick"><slot /></a>
</template>
