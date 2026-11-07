<script setup lang="ts">
/** 全站线性图标：1.5px 描边、直角收笔，颜色跟随 currentColor（不引图标库） */
import { ICON_PATHS, type IconName } from './lineIcons'

withDefaults(defineProps<{ name: IconName; size?: number }>(), { size: 16 })
</script>

<template>
  <svg
    :width="size" :height="size" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="1.5" stroke-linecap="square" stroke-linejoin="miter"
    aria-hidden="true" class="shrink-0"
  >
    <path v-for="(d, i) in ICON_PATHS[name] ?? []" :key="i" :d="d" />
  </svg>
</template>
