<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'

const props = defineProps<{ images: string[]; start: number }>()
const emit = defineEmits<{ (e: 'close'): void }>()
const idx = defineModel<number>('index')

const src = computed(() => props.images[idx.value ?? 0])

function step(d: number) {
  idx.value = ((idx.value ?? 0) + d + props.images.length) % props.images.length
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
  if (e.key === 'ArrowRight') step(1)
  if (e.key === 'ArrowLeft') step(-1)
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div
    class="fixed inset-0 z-[100] flex items-center justify-center bg-black/90"
    @click.self="emit('close')"
  >
    <img :src="src" alt="" class="max-h-[90vh] max-w-[92vw] object-contain" />
    <button class="absolute left-4 top-1/2 -translate-y-1/2 p-3 text-3xl text-white/70 hover:text-white" aria-label="上一张" @click="step(-1)">‹</button>
    <button class="absolute right-4 top-1/2 -translate-y-1/2 p-3 text-3xl text-white/70 hover:text-white" aria-label="下一张" @click="step(1)">›</button>
    <button class="absolute right-4 top-4 p-2 text-2xl text-white/70 hover:text-white" aria-label="关闭" @click="emit('close')">×</button>
    <p class="absolute bottom-5 left-1/2 -translate-x-1/2 text-xs text-white/60">{{ (idx ?? 0) + 1 }} / {{ images.length }}</p>
  </div>
</template>
