<script setup lang="ts">
import { useHead } from '@unhead/vue'
import { RouterView } from 'vue-router'
import { computed, watch } from 'vue'
import { siteApi } from '@/api'
import { useAsync } from '@/composables/useAsync'
import { fallback, useSiteStore } from '@/stores/site'

const DEFAULT_FAVICON = '/favicon.svg'

const site = useSiteStore()
const cfg = useAsync(() => siteApi.config(), 'site-config')
// flush:'sync' 是必需的：SSG 下数据要等 onServerPrefetch 落进 cfg.data，默认的 pre 调度
// 会排到本次渲染之后 —— 预渲染 HTML 里站名/导航/首屏介绍就全是 fallback 文案（实测踩过）。
watch(() => cfg.data.value, (v) => { if (v) site.config = v }, { immediate: true, flush: 'sync' })

// 标签页图标挂在 App 而不是 useSeo：后者只在站点页调用，后台页会漏掉这条
useHead({
  link: computed(() => [{ rel: 'icon', href: (site.config ?? fallback).site.favicon || DEFAULT_FAVICON }]),
})
</script>

<template>
  <RouterView />
</template>
