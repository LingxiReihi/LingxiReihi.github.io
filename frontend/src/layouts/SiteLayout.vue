<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

import { useThemeStore } from '@/stores/theme'
import { fallback, useSiteStore } from '@/stores/site'
import { usePageTransition } from '@/composables/usePageTransition'
import CharBounce from '@/components/common/CharBounce.vue'
import DynamicBackground from '@/components/site/DynamicBackground.vue'
import ScrollRuler from '@/components/site/ScrollRuler.vue'
import SiteSearch from '@/components/site/SiteSearch.vue'

const theme = useThemeStore()
const site = useSiteStore()
const route = useRoute()
const { onEnter, onLeave } = usePageTransition()
const mobileOpen = ref(false)
const mainEl = ref<HTMLElement | null>(null)
const ruler = ref<InstanceType<typeof ScrollRuler> | null>(null)

watch(
  () => route.path,
  async () => {
    mobileOpen.value = false
    // 内容滚动发生在 main 内部，路由切换时手动回到顶部
    mainEl.value?.scrollTo({ top: 0 })
    // 新页面高度不同，等渲染完再量一次刻度尺
    await nextTick()
    ruler.value?.refresh()
  },
)

const navItems = computed(() => (site.config ?? fallback).nav_items.filter((i) => i.visible))
const siteTitle = computed(() => (site.config ?? fallback).site.title)
const isActive = (path: string) =>
  path === '/' ? route.path === '/' : route.path.startsWith(path)
</script>

<template>
  <div class="hud-grid relative flex h-svh flex-col overflow-hidden bg-bg text-ink">
    <DynamicBackground />
    <header class="relative z-40 shrink-0 border-b border-line bg-surface/95 backdrop-blur">
      <div class="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
        <RouterLink to="/" :aria-label="siteTitle" class="font-mono text-[13px] font-semibold tracking-[0.16em] text-brand-2"><CharBounce :text="siteTitle" /></RouterLink>
        <nav class="hidden md:flex items-center gap-0.5">
          <RouterLink
            v-for="(item, i) in navItems" :key="item.path" :to="item.path"
            :aria-label="item.label"
            class="font-mono text-[11px] uppercase tracking-[0.16em] border px-2.5 py-1.5 transition-colors"
            :class="isActive(item.path)
              ? 'border-brand bg-brand text-[#04110f] font-semibold'
              : 'border-transparent text-ink-2 hover:border-line hover:text-ink'"
          ><CharBounce :text="item.label" :start="300 + i * 70" /></RouterLink>
        </nav>
        <div class="ml-auto flex items-center gap-2">
          <div class="hidden sm:block">
            <SiteSearch />
          </div>
          <button
            class="grid h-8 w-8 place-items-center border border-line text-[13px] text-ink-2 transition-colors hover:border-brand hover:text-brand"
            :aria-label="theme.mode === 'dark' ? '切换到亮色' : '切换到暗色'"
            @click="theme.toggle()"
          >{{ theme.mode === 'dark' ? '☀️' : '🌙' }}</button>
          <button
            class="md:hidden grid h-8 w-8 place-items-center border border-line text-[13px] text-ink-2"
            aria-label="菜单" :aria-expanded="mobileOpen"
            @click="mobileOpen = !mobileOpen"
          >☰</button>
        </div>
      </div>
      <!-- 悬浮菜单面板：绝对定位，不占页面高度 -->
      <Transition
        enter-active-class="transition duration-150 ease-out"
        enter-from-class="opacity-0 -translate-y-1"
        leave-active-class="transition duration-100 ease-in"
        leave-to-class="opacity-0 -translate-y-1"
      >
        <nav
          v-if="mobileOpen"
          class="absolute right-3 top-full z-50 mt-2 w-56 border border-line bg-surface p-1.5 shadow-2xl md:hidden"
        >
          <div class="p-1.5 pb-3"><SiteSearch /></div>
          <RouterLink
            v-for="item in navItems" :key="item.path" :to="item.path"
            class="block px-3 py-2 font-mono text-[11px] uppercase tracking-[0.16em]"
            :class="isActive(item.path) ? 'bg-brand font-semibold text-[#04110f]' : 'text-ink-2 hover:bg-elevated'"
          >{{ item.label }}</RouterLink>
        </nav>
      </Transition>
    </header>
    <main ref="mainEl" class="relative z-10 min-h-0 flex-1 overflow-y-auto">
      <RouterView v-slot="{ Component }">
        <Transition mode="out-in" :css="false" @enter="onEnter" @leave="onLeave">
          <component :is="Component" />
        </Transition>
      </RouterView>
    </main>
    <ScrollRuler ref="ruler" :target="mainEl" />
    <footer class="relative z-10 flex shrink-0 items-center justify-between border-t border-line px-4 py-3 font-mono text-[10px] uppercase tracking-[0.16em] text-ink-3">
      <span>© {{ new Date().getFullYear() }} {{ siteTitle }}</span>
      <span class="flex items-center gap-4">
        <a class="transition-colors hover:text-brand" href="/feed.xml">RSS</a>
        <a class="transition-colors hover:text-brand" href="/sitemap.xml">Sitemap</a>
      </span>
    </footer>
  </div>
</template>

<style scoped>
/* 滚动条隐藏（圈注）：main 是唯一滚动区，移动端常驻滚动条遮挡内容 */
main {
  scrollbar-width: none;
}
main::-webkit-scrollbar {
  display: none;
}
</style>
