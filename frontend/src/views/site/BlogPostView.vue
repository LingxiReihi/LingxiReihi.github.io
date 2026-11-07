<script setup lang="ts">
import { postsApi } from '@/api'
import ClientOnly from '@/components/common/ClientOnly.vue'
import ErrorRetry from '@/components/common/ErrorRetry.vue'
import SkeletonBlock from '@/components/common/SkeletonBlock.vue'
import TocNav from '@/components/site/TocNav.vue'
import { useAsync } from '@/composables/useAsync'
import { renderMd } from '@/composables/useMd'
import { useSeo } from '@/composables/useSeo'
import { enhanceCodeBlocks } from '@/composables/useCodeEnhance'
import { useSiteTitle } from '@/stores/site'
import { formatDate } from '@/utils/format'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import LineIcon from '@/components/common/LineIcon.vue'

const route = useRoute()
const slug = computed(() => String(route.params.slug))
const previewToken = computed(() => (route.query.preview ? String(route.query.preview) : null))
const state = useAsync(() =>
  previewToken.value ? postsApi.preview(slug.value, previewToken.value!) : postsApi.detail(slug.value),
  `post:${slug.value}`)

const html = computed(() => (state.data.value ? renderMd(state.data.value.body_md).html : ''))
const toc = computed(() => (state.data.value ? renderMd(state.data.value.body_md).toc : []))

useSeo({
  title: computed(() => state.data.value?.title ?? '文章'),
  siteTitle: useSiteTitle(),
  description: computed(() => state.data.value?.summary),
  path: computed(() => `/blog/${slug.value}`),
  image: computed(() => state.data.value?.cover),
  type: 'article',
})

// 阅读进度改由站点级右缘刻度尺承担（components/site/ScrollRuler.vue，挂在 SiteLayout）

// 代码块增强：语言栏 + 复制 + Shiki 双主题高亮（客户端，SSG 文本已在 HTML 中）
const tocOpen = ref(false)
const copied = ref(false)
const proseRef = ref<HTMLElement | null>(null)

/** #<标题 id>：目录深链；找不到 id 时按 data-a 原文兜底 */
function scrollToHeading(el: HTMLElement) {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  el.scrollIntoView({ behavior: reduced ? 'instant' : 'smooth', block: 'start' })
  el.classList.add('anchor-hit')
  window.setTimeout(() => el.classList.remove('anchor-hit'), 1600)
}

async function focusHash(): Promise<boolean> {
  if (typeof window === 'undefined') return false
  let hash = ''
  try {
    hash = decodeURIComponent(window.location.hash.slice(1))
  } catch {
    return false
  }
  if (!hash) return false
  await nextTick()
  const root = proseRef.value
  if (!root) return false
  const byId = document.getElementById(hash)
  const el = byId && root.contains(byId)
    ? byId
    : [...root.querySelectorAll<HTMLElement>('[data-a]')]
        .find((h) => h.dataset.a === hash)
  if (!el) return false
  scrollToHeading(el)
  return true
}

function onHashChange() { void focusHash() }

watch(
  () => [state.data.value, html.value] as const,
  ([d]) => {
    if (!d) return
    nextTick(async () => {
      if (proseRef.value) enhanceCodeBlocks(proseRef.value)
      await focusHash()
    })
  },
  { immediate: true },
)

// 上下篇跳转复用组件时按 slug 重新拉取
watch([slug, previewToken], () => state.retry())

async function copyLink() {
  await navigator.clipboard.writeText(window.location.href)
  copied.value = true
  setTimeout(() => (copied.value = false), 2000)
}

// 点击图片看大图（灯箱）：prose 容器事件委托，Esc/点击遮罩关闭
const lightbox = ref<string | null>(null)
function onProseClick(e: MouseEvent) {
  const t = e.target as HTMLElement
  if (t.tagName === 'IMG' && lightbox.value === null) lightbox.value = t.getAttribute('src')
}
function closeLightbox() {
  lightbox.value = null
}
function onLightboxKey(e: KeyboardEvent) {
  if (e.key === 'Escape') closeLightbox()
}
watch(lightbox, (v) => {
  if (v) window.addEventListener('keydown', onLightboxKey)
  else window.removeEventListener('keydown', onLightboxKey)
})
onMounted(() => window.addEventListener('hashchange', onHashChange))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onLightboxKey)
  window.removeEventListener('hashchange', onHashChange)
})
</script>

<template>
  <div>
    <ErrorRetry v-if="state.error.value" :message="state.error.value" @retry="state.retry" />
    <SkeletonBlock v-else-if="state.loading.value" :lines="8" class="mx-auto max-w-3xl px-4 py-16" />
    <template v-else-if="state.data.value">
      <div class="mx-auto flex max-w-[1200px] gap-10 px-4 py-12">
        <article class="min-w-0 flex-1">
          <h1 class="text-3xl font-bold leading-snug">{{ state.data.value.title }}</h1>
          <div class="mt-4 flex flex-wrap items-center gap-2 text-sm text-ink-3">
            <template v-if="state.data.value.author?.nickname">
              <RouterLink
                :to="{ path: '/about', query: { a: state.data.value.author.nickname } }"
                title="查看这位管理员的介绍"
                class="flex items-center gap-1.5 transition-colors hover:text-brand"
              >
                <img
                  v-if="state.data.value.author.avatar" :src="state.data.value.author.avatar" alt=""
                  class="h-5 w-5 rounded-full border border-line object-cover"
                >{{ state.data.value.author.nickname }}
              </RouterLink>
              <span>·</span>
            </template>
            <time>{{ formatDate(state.data.value.published_at) }}</time>
            <span v-if="state.data.value.extra.reading_time">· ≈{{ state.data.value.extra.reading_time }} 分钟</span>
            <RouterLink
              v-if="state.data.value.column"
              :to="`/blog?column=${encodeURIComponent(state.data.value.column.slug)}`"
              class="rounded-full bg-brand/15 px-2 py-0.5 text-xs text-brand transition-colors hover:bg-brand/25"
            ><LineIcon name="folder" :size="12" class="mr-1 inline align-[-1px]" />{{ state.data.value.column.name }}</RouterLink>
            <RouterLink
              v-for="t in state.data.value.tags" :key="t.id"
              :to="`/blog?tag=${encodeURIComponent(t.slug)}`"
              class="rounded-full border border-line px-2 py-0.5 text-xs transition-colors hover:border-brand hover:text-brand"
            >{{ t.name }}</RouterLink>
          </div>
          <img v-if="state.data.value.cover" :src="state.data.value.cover" :alt="state.data.value.title" class="mt-6 w-full rounded-xl border border-line" />
          <!-- eslint-disable-next-line vue/no-v-html -- MD 源仅作者自己（html:false 已转义） -->
          <div ref="proseRef" class="prose mt-8" v-html="html" @click="onProseClick" />
          <Teleport to="body">
            <div
              v-if="lightbox" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/85 p-4"
              role="dialog" aria-label="图片大图" @click="closeLightbox"
            >
              <img :src="lightbox" alt="" class="max-h-full max-w-full rounded-lg bg-surface object-contain" @click.stop />
              <button class="absolute right-4 top-4 flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-surface text-ink" aria-label="关闭大图" @click="closeLightbox">✕</button>
            </div>
          </Teleport>
          <ClientOnly>
            <div class="mt-10 flex flex-wrap items-center gap-3">
              <button class="inline-flex items-center gap-1.5 rounded-lg border border-line px-4 py-2 text-sm text-ink-2 hover:bg-elevated" @click="copyLink">
                <LineIcon name="link" :size="13" />{{ copied ? '已复制链接 ✓' : '复制链接' }}
              </button>
            </div>
          </ClientOnly>

          <nav class="mt-10 grid gap-4 border-t border-line pt-8 sm:grid-cols-2">
            <RouterLink v-if="state.data.value.prev" :to="`/blog/${state.data.value.prev.slug}`" class="group rounded-xl border border-line p-4 hover:border-brand/40">
              <p class="text-xs text-ink-3">← 上一篇</p>
              <p class="mt-1 font-medium group-hover:text-brand">{{ state.data.value.prev.title }}</p>
            </RouterLink>
            <RouterLink v-if="state.data.value.next" :to="`/blog/${state.data.value.next.slug}`" class="group rounded-xl border border-line p-4 text-right hover:border-brand/40">
              <p class="text-xs text-ink-3">下一篇 →</p>
              <p class="mt-1 font-medium group-hover:text-brand">{{ state.data.value.next.title }}</p>
            </RouterLink>
          </nav>

          <section v-if="state.data.value.related.length" class="mt-10">
            <h2 class="mb-4 text-lg font-bold">相关建议</h2>
            <ul class="space-y-2">
              <li v-for="r in state.data.value.related" :key="r.id">
                <RouterLink :to="`/blog/${r.slug}`" class="text-sm text-ink-2 hover:text-brand">· {{ r.title }}</RouterLink>
              </li>
            </ul>
          </section>
        </article>

        <!-- 右侧目录改由站点级右缘刻度尺承担（components/site/ScrollRuler.vue）：
             这里只留同宽的占位，保持正文宽度不变，避免与右缘列表重叠 -->
        <div class="hidden w-56 shrink-0 xl:block" aria-hidden="true" />
      </div>

      <!-- <1280px 浮动目录按钮 -->
      <ClientOnly>
        <template v-if="toc.length">
          <button
            class="fixed bottom-6 right-6 z-40 rounded-full border border-line bg-surface p-3 shadow-lg xl:hidden"
            aria-label="打开目录"
            @click="tocOpen = !tocOpen"
          >☰ 目录</button>
          <div v-if="tocOpen" class="fixed bottom-20 right-6 z-40 max-h-[50vh] w-64 overflow-auto rounded-xl border border-line bg-surface p-4 shadow-xl xl:hidden">
            <TocNav :items="toc" />
          </div>
        </template>
      </ClientOnly>
    </template>
  </div>
</template>

<style scoped>
:deep(.prose [data-a].anchor-hit) {
  outline: 2px solid var(--c-primary);
  outline-offset: 5px;
  border-radius: 4px;
}
</style>
