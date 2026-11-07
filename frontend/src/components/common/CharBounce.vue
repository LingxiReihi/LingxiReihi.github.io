<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'

/**
 * 顶栏文字逐字符跳动。
 *
 * 首帧（含 vite-ssg 预渲染）输出纯文本，挂载后才换成逐字符节点 —— 否则收录 HTML 里
 * 的「泠曦 Blog」会变成一串碎片，百度这类蜘蛛对断开文本的容忍度比 Google 低。
 * 字符节点由 v-for 持有，所以站点设置里改站名/导航名会正常重渲染；
 * 动画只写这些 span 的 transform，不碰文本节点（这是之前 scrambleText 踩过的坑）。
 */
const props = defineProps<{ text: string; start?: number }>()
const live = ref(false)
const root = ref<HTMLElement | null>(null)
const chars = computed(() => Array.from(props.text))

const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

function targets(): HTMLElement[] {
  return [...(root.value?.querySelectorAll<HTMLElement>('[data-char]') ?? [])]
}

async function play(mode: 'in' | 'wave') {
  const els = targets()
  if (!els.length || reduced()) return
  const { animate } = await import('animejs')
  els.forEach((el, i) => {
    if (mode === 'in') {
      animate(el, { opacity: [0, 1], translateY: [14, 0], duration: 420, ease: 'outQuad', delay: (props.start ?? 0) + i * 38 })
    } else {
      animate(el, { translateY: [-6, 0], duration: 320, ease: 'outQuad', delay: i * 28 })
    }
  })
}

onMounted(() => {
  live.value = true
  nextTick(() => play('in'))
})
watch(() => props.text, () => nextTick(() => play('in')))
</script>

<template>
  <span v-if="!live">{{ text }}</span>
  <span v-else ref="root" aria-hidden="true" @mouseenter="play('wave')"
  ><i v-for="(c, i) in chars" :key="i" data-char class="inline-block whitespace-pre not-italic">{{ c }}</i></span>
</template>
