<script setup lang="ts">
withDefaults(defineProps<{
  title?: string
  hint?: string
  icon?: string
  ctaLabel?: string
}>(), { title: '暂无内容', hint: '', icon: '🌊', ctaLabel: '' })
const emit = defineEmits<{ (e: 'action'): void }>()
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-3 py-16 text-center">
    <div class="text-4xl" aria-hidden="true">{{ icon }}</div>
    <p class="font-medium">{{ title }}</p>
    <p v-if="hint" class="max-w-sm text-sm text-ink-3">{{ hint }}</p>
    <button
      v-if="ctaLabel"
      class="mt-2 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-black transition-opacity hover:opacity-90"
      @click="emit('action')"
    >{{ ctaLabel }}</button>
  </div>
</template>
