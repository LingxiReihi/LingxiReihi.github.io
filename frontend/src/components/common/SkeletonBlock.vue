<script setup lang="ts">
withDefaults(defineProps<{ lines?: number; height?: string }>(), { lines: 3, height: '1rem' })
</script>

<template>
  <div class="space-y-3" aria-hidden="true">
    <div
      v-for="i in lines" :key="i"
      class="animate-pulse rounded-lg bg-elevated"
      :style="{ height, width: i === lines ? '60%' : '100%' }"
    />
  </div>
</template>
