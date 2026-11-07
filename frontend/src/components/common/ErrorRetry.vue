<script setup lang="ts">
defineProps<{ message?: string }>()
const emit = defineEmits<{ (e: 'retry'): void }>()
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-3 py-14 text-center">
    <div class="text-3xl" aria-hidden="true">⚠️</div>
    <p class="text-sm text-ink-2">{{ message || '加载失败，请检查网络后重试' }}</p>
    <button
      class="rounded-lg border border-line px-4 py-1.5 text-sm hover:bg-elevated"
      @click="emit('retry')"
    >重试</button>
  </div>
</template>
