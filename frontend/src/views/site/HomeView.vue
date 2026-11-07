<script setup lang="ts">
import type { HomeData } from '@/api/types'
import { homeApi, modelsApi, postsApi } from '@/api'
import ErrorRetry from '@/components/common/ErrorRetry.vue'
import HomeTeamStrip from '@/components/home/HomeTeamStrip.vue'
import SkeletonBlock from '@/components/common/SkeletonBlock.vue'
import { useAsync } from '@/composables/useAsync'
import { mdInlineToText, renderMdInline } from '@/composables/useMd'
import { useReveal } from '@/composables/useReveal'
import { decodeText } from '@/composables/useScramble'
import { useSeo } from '@/composables/useSeo'
import { fallback, useSiteStore } from '@/stores/site'
import { contentLink, safeExternalUrl, TYPE_LABEL } from '@/utils/link'
import { formatDate } from '@/utils/format'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const state = useAsync(() => homeApi.get(), 'home')
const site = useSiteStore()
const data = computed<HomeData | null>(() => state.data.value ?? null)
const loading = computed(() => state.loading.value ?? false)
const error = computed(() => state.error.value ?? null)

useSeo({
  title: '首页',
  siteTitle: computed(() => (site.config ?? fallback).site.title),
  path: '/',
  // 描述现在允许行内 Markdown，而 meta/og 里不能带标记，先还原成纯文本
  description: computed(() => mdInlineToText((site.config ?? fallback).site.description ?? '')),
})

/** 首屏是「网站介绍」而非个人介绍：三项全部复用后台「站点设置 → 站点信息」，不新增字段。
 *  副标题留空时整行不渲染（而不是回落到某个写死的眉题）。 */
const intro = computed(() => {
  const s = (site.config ?? fallback).site
  return { eyebrow: s.subtitle, title: s.title, body: s.description }
})

/** 简介按行内 Markdown 渲染（链接/加粗/斜体/行内代码）；块级语法不生效，见 renderMdInline。 */
const introHtml = computed(() => renderMdInline(intro.value.body ?? ''))

/** 友站跳转：数据源就是后台「导航与页脚 → 页脚链接」那一组（footer.links），不新增字段。
 *  没填链接名就用对方域名顶上，免得首屏出现一个空白可点区。 */
const friends = computed(() => {
  return ((site.config ?? fallback).footer.links ?? [])
    .map((l) => {
      const url = safeExternalUrl(l.url)
      if (!url) return null
      let label = l.platform?.trim()
      if (!label) {
        try { label = new URL(url).hostname } catch { return null }
      }
      return { url, label }
    })
    .filter((f): f is { url: string; label: string } => f !== null)
})

// 每段各占一页（不足补空白、内容垂直居中），滚到段尾吸附到下一段开头
const heroInner = ref<HTMLElement | null>(null)
const heroEyebrow = ref<HTMLElement | null>(null)
const heroTitle = ref<HTMLElement | null>(null)
const heroSig = ref<HTMLElement | null>(null)
const { refresh } = useReveal()
watch(data, () => nextTick(refresh))
// 站点信息可能晚于挂载到达（无 SSG 种子的场景），文案变了就把介绍重解码一次
watch(intro, () => nextTick(playHero))

/** 最新最多 10 条（后端 latest 给 12，这里只裁不补） */
const MAX_ITEMS = 10
const latest = computed(() => data.value?.latest.slice(0, MAX_ITEMS) ?? [])
/** 首页索引表一屏只放 8 行，多的去 /blog */
const latestRows = computed(() => latest.value.slice(0, 8))

/** 首页「内容分区」：模型没有现成 home 字段，单独取 4 条（SSG 期预取，客户端读种子） */
const modelsState = useAsync(() => modelsApi.list({ page_size: 4 }), 'home-models')
const recentModels = computed(() => modelsState.data.value?.items ?? [])

/** 右侧数据面板：文章/作品总数各用一次 page_size=1 的轻请求拿 total，失败就不显示 */
const counts = ref<{ posts: number; models: number } | null>(null)
const countState = ref({ posts: false, models: false })
onMounted(() => {
  postsApi.list({ page_size: 1 })
    .then((d) => { counts.value = { ...(counts.value ?? { posts: 0, models: 0 }), posts: d.total }; countState.value.posts = true })
    .catch(() => {})
  modelsApi.list({ page_size: 1 })
    .then((d) => { counts.value = { ...(counts.value ?? { posts: 0, models: 0 }), models: d.total }; countState.value.models = true })
    .catch(() => {})
})
const lastUpdated = computed(() => formatDate(latest.value[0]?.published_at) || '—')
/** 0 也要显示成 0（站点确实没有作品时不能空着） */
const num = (v: number | undefined, loaded: boolean) => (loaded && v !== undefined ? String(v) : '—')
const stats = computed(() => [
  { k: num(counts.value?.posts, countState.value.posts), label: 'Articles', sub: '已发布文章' },
  { k: num(counts.value?.models, countState.value.models), label: 'Works', sub: '模型 / 渲染' },
  { k: String(data.value?.team.length ?? '—'), label: 'Members', sub: '管理团队' },
  { k: lastUpdated.value, label: 'Updated', sub: '最近更新', small: true },
])

const reduced = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
let scroller: HTMLElement | null = null
let raf = 0
let jumping = false
let lastTop = 0

/** 段相对滚动容器顶部的偏移（不用 offsetTop：它取决于最近定位祖先，这里三层嵌套会变） */
function pageTop(el: HTMLElement): number {
  const s = scroller
  if (!s) return 0
  return s.scrollTop + el.getBoundingClientRect().top - s.getBoundingClientRect().top
}

function pages(): HTMLElement[] {
  return [...document.querySelectorAll<HTMLElement>('.home-page')]
}

/**
 * 下一段的标题一进视口就整段切过去（不是等滚到底、也不靠 CSS 吸附 —— 吸附只按「离哪个边界近」
 * 决定，标题出现时往往还差半屏）。**只在向下滚时触发**：站在段首往上滑一点，下一段标题其实还在
 * 视口里，不分方向就会立刻把人拽回去，等于给上滑装了棘轮（用户实测反馈「上滑阻力太大」即此）。
 */
function maybePaging(down: boolean) {
  const s = scroller
  if (!s || jumping || reduced || !down) return
  const list = pages()
  const top = s.scrollTop
  let cur = 0
  // pageTop 是「该段对齐到视口顶时应有的 scrollTop」（文档坐标），所以要和 scrollTop 比，
  // 不是和 0 比 —— 之前写成 <=8 会让 cur 永远停在第一段，往下翻反而被拽回首段
  list.forEach((p, i) => { if (pageTop(p) <= top + 8) cur = i })
  const next = list[cur + 1]
  const title = next?.querySelector<HTMLElement>('h1, h2')
  if (!title) return
  if (title.getBoundingClientRect().top - s.getBoundingClientRect().top < s.clientHeight - 24) jumpTo(next)
}

function jumpTo(el: HTMLElement) {
  const s = scroller
  if (!s) return
  jumping = true
  s.scrollTo({ top: pageTop(el), behavior: 'smooth' })
  const done = () => { jumping = false }
  // 平滑滚动没有可靠的完成事件：支持 scrollend 就用它，否则给足时间兜底，别把翻页永久锁死
  if ('onscrollend' in window) s.addEventListener('scrollend', done, { once: true })
  window.setTimeout(done, 1200)
}

/** 滚动擦洗一律手写插值：anime 实例在 autoplay:false + seek 的路线上不可靠（见 docs 教训） */
function onScroll() {
  if (raf) return
  raf = requestAnimationFrame(() => {
    raf = 0
    const s = scroller
    if (!s) return
    const top = s.scrollTop
    const down = top > lastTop
    lastTop = top
    maybePaging(down)
    const el = heroInner.value
    if (!el || reduced) return
    const p = Math.min(1, Math.max(0, top / (s.clientHeight * 0.7)))
    const e = p * p
    el.style.opacity = String(1 - e)
    el.style.transform = `translate3d(0, ${-46 * e}px, 0)`
  })
}

/** 一页多高只有滚动容器自己知道：写成变量给 .home-page 用，100svh 会顶穿顶栏与页脚 */
function syncPageHeight() {
  scroller?.style.setProperty('--pw-home-page', `${scroller.clientHeight}px`)
}

function playHero() {
  decodeText(heroEyebrow.value, { delay: 0, duration: 460 })
  decodeText(heroTitle.value, { delay: 120, duration: 620 })
  decodeText(heroSig.value, { delay: 420, duration: 760 })
}

onMounted(() => {
  scroller = heroInner.value?.closest('main') ?? null
  if (scroller) {
    syncPageHeight()
    scroller.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', syncPageHeight)
  }
  nextTick(playHero)
})
onBeforeUnmount(() => {
  scroller?.removeEventListener('scroll', onScroll)
  scroller?.style.removeProperty('--pw-home-page')
  window.removeEventListener('resize', syncPageHeight)
  if (raf) cancelAnimationFrame(raf)
})
</script>

<template>
  <div>
    <section class="home-page flex items-center overflow-hidden">
      <div ref="heroInner" class="mx-auto w-full max-w-6xl px-4">
        <div class="grid items-center gap-10 lg:grid-cols-[1.25fr_.75fr]">
          <div>
            <p v-if="intro.eyebrow" ref="heroEyebrow" class="mb-3 font-mono text-[10px] uppercase tracking-[0.24em] text-brand">{{ intro.eyebrow }}</p>
            <h1 ref="heroTitle" class="text-4xl font-bold leading-[1.14] tracking-tight md:text-5xl">{{ intro.title }}</h1>
            <p ref="heroSig" class="home-intro mt-4 max-w-xl text-base text-ink-2 md:text-lg" v-html="introHtml"></p>
            <div class="mt-8 flex flex-wrap gap-2.5">
              <RouterLink to="/blog" class="border border-brand bg-brand px-5 py-2.5 font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[#04110f]">阅读博客 →</RouterLink>
              <RouterLink to="/models" class="border border-line px-5 py-2.5 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-2 transition-colors hover:border-brand hover:text-brand">查看作品</RouterLink>
            </div>
            <div v-if="friends.length" class="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2">
              <span class="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-3">友站</span>
              <a v-for="f in friends" :key="f.url" :href="f.url"
                 target="_blank" rel="noopener noreferrer"
                 class="text-[13px] text-ink-2 underline decoration-line underline-offset-4 transition-colors hover:text-brand">{{ f.label }}</a>
            </div>
          </div>
          <!-- 数据面板：把首页右半做成仪器读数，数字全部来自真实接口 -->
          <div class="hidden lg:block">
            <div class="relative border border-line bg-surface/30">
              <span class="pointer-events-none absolute left-0 top-0 h-2.5 w-2.5 border-l border-t border-brand" aria-hidden="true" />
              <span class="pointer-events-none absolute bottom-0 right-0 h-2.5 w-2.5 border-b border-r border-brand" aria-hidden="true" />
              <div class="flex items-center justify-between border-b border-line px-4 py-2">
                <span class="font-mono text-[9px] uppercase tracking-[0.24em] text-ink-3">Status</span>
                <span class="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.18em] text-brand">
                  <i class="h-1.5 w-1.5 bg-brand" style="box-shadow: 0 0 8px var(--c-primary)" />Online
                </span>
              </div>
              <div class="grid grid-cols-2 gap-px bg-line">
                <div v-for="s in stats" :key="s.label" class="bg-bg/70 px-4 py-4">
                  <p class="font-mono font-semibold leading-none text-ink" :class="s.small ? 'text-base' : 'text-2xl'">{{ s.k }}</p>
                  <p class="mt-2.5 font-mono text-[9px] uppercase tracking-[0.2em] text-brand/80">{{ s.label }}</p>
                  <p class="mt-1 text-[11px] text-ink-3">{{ s.sub }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="home-page flex items-center">
      <div class="mx-auto w-full max-w-6xl px-4">
        <ErrorRetry v-if="error" :message="error" @retry="state.retry" />
        <SkeletonBlock v-else-if="loading" :lines="6" height="2.6rem" />
        <template v-else>
          <header class="flex items-end justify-between border-b border-line pb-3">
            <h2 class="flex items-baseline gap-2.5">
              <span class="font-mono text-[10px] tracking-[0.24em] text-brand">//</span>
              <span class="text-lg font-bold tracking-tight md:text-xl">最新内容</span>
              <span class="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-3">{{ latest.length }} 条</span>
            </h2>
            <RouterLink to="/blog" class="font-mono text-[10px] uppercase tracking-[0.16em] text-brand hover:underline">全部文章 →</RouterLink>
          </header>
          <!-- 索引表：编号 / 标题 / 类型 / 日期，比卡片墙更接近仪器读数 -->
          <div class="mt-1">
            <RouterLink
              v-for="(p, i) in latestRows" :key="p.id" :to="contentLink(p)" data-reveal
              class="group grid grid-cols-[32px_1fr_76px] items-baseline gap-4 border-b border-line/60 py-3 transition-colors hover:bg-elevated/30 md:grid-cols-[32px_1fr_92px_84px]"
            >
              <span class="font-mono text-[10px] text-brand/70">{{ String(i + 1).padStart(2, '0') }}</span>
              <span class="truncate text-sm font-medium transition-colors group-hover:text-brand md:text-[15px]">{{ p.title }}</span>
              <span class="hidden font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3 md:block">{{ TYPE_LABEL[p.type] }}</span>
              <span class="text-right font-mono text-[10px] tracking-[0.06em] text-ink-3">{{ formatDate(p.published_at) }}</span>
            </RouterLink>
          </div>
        </template>
      </div>
    </section>

    <section v-if="data" class="home-page flex items-center">
      <div class="mx-auto w-full max-w-6xl px-4">
        <header class="mb-5 flex items-end justify-between border-b border-line pb-3">
          <h2 class="flex items-baseline gap-2.5">
            <span class="font-mono text-[10px] tracking-[0.24em] text-brand">//</span>
            <span class="text-lg font-bold tracking-tight md:text-xl">内容分区</span>
          </h2>
          <span class="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-3">Blog · Models · Chats</span>
        </header>

        <div class="grid gap-px border border-line bg-line md:grid-cols-3">
          <section class="flex min-h-52 flex-col bg-bg/70 p-5">
            <p class="font-mono text-[9px] uppercase tracking-[0.24em] text-brand/80">01 / Blog</p>
            <h3 class="mt-2 text-base font-bold">博客</h3>
            <p class="mt-1 text-xs text-ink-3">长文与教程{{ counts ? ` · 共 ${counts.posts} 篇` : '' }}</p>
            <ul class="mt-4 space-y-2">
              <li v-for="p in data.recent_posts" :key="p.id">
                <RouterLink :to="`/blog/${p.slug}`" class="group flex items-baseline gap-3 text-sm">
                  <span class="font-mono text-[10px] text-ink-3">{{ formatDate(p.published_at) }}</span>
                  <span class="min-w-0 flex-1 truncate text-ink-2 transition-colors group-hover:text-brand">{{ p.title }}</span>
                </RouterLink>
              </li>
            </ul>
            <RouterLink to="/blog" class="mt-auto pt-4 font-mono text-[10px] uppercase tracking-[0.16em] text-brand hover:underline">全部文章 →</RouterLink>
          </section>

          <section class="flex min-h-52 flex-col bg-bg/70 p-5">
            <p class="font-mono text-[9px] uppercase tracking-[0.24em] text-brand/80">02 / Models</p>
            <h3 class="mt-2 text-base font-bold">模型</h3>
            <p class="mt-1 text-xs text-ink-3">3D · 渲染 · 动画{{ counts ? ` · 共 ${counts.models} 件` : '' }}</p>
            <ul v-if="recentModels.length" class="mt-4 space-y-2">
              <li v-for="m in recentModels" :key="m.id">
                <RouterLink :to="`/models/${m.slug}`" class="group flex items-baseline gap-3 text-sm">
                  <span class="font-mono text-[10px] text-ink-3">{{ formatDate(m.published_at) }}</span>
                  <span class="min-w-0 flex-1 truncate text-ink-2 transition-colors group-hover:text-brand">{{ m.title }}</span>
                </RouterLink>
              </li>
            </ul>
            <p v-else class="mt-4 text-sm text-ink-3">{{ modelsState.loading.value ? '加载中…' : '暂无作品' }}</p>
            <RouterLink to="/models" class="mt-auto pt-4 font-mono text-[10px] uppercase tracking-[0.16em] text-brand hover:underline">查看作品 →</RouterLink>
          </section>

          <section class="flex min-h-52 flex-col bg-bg/70 p-5">
            <p class="font-mono text-[9px] uppercase tracking-[0.24em] text-brand/80">03 / Chats</p>
            <h3 class="mt-2 text-base font-bold">杂谈</h3>
            <p class="mt-1 text-xs text-ink-3">碎片想法与日常</p>
            <ul class="mt-4 space-y-2">
              <li v-for="c in data.recent_chats" :key="c.id">
                <RouterLink :to="`/chats/${c.id}`" class="group flex items-baseline gap-3 text-sm">
                  <span class="font-mono text-[10px] text-ink-3">{{ formatDate(c.published_at) }}</span>
                  <span class="min-w-0 flex-1 truncate text-ink-2 transition-colors group-hover:text-brand">{{ c.title }}</span>
                </RouterLink>
              </li>
            </ul>
            <RouterLink to="/chats" class="mt-auto pt-4 font-mono text-[10px] uppercase tracking-[0.16em] text-brand hover:underline">全部杂谈 →</RouterLink>
          </section>
        </div>
      </div>
    </section>

    <section v-if="data" class="home-page flex items-center">
      <div class="mx-auto w-full max-w-6xl px-4">
        <header class="mb-5 flex items-end justify-between border-b border-line pb-3">
          <h2 class="flex items-baseline gap-2.5">
            <span class="font-mono text-[10px] tracking-[0.24em] text-brand">//</span>
            <span class="text-lg font-bold tracking-tight md:text-xl">管理团队</span>
          </h2>
          <RouterLink to="/about" class="font-mono text-[10px] uppercase tracking-[0.16em] text-brand hover:underline">关于页 →</RouterLink>
        </header>
        <HomeTeamStrip layout="grid" :members="data.team" />
      </div>
    </section>
  </div>
</template>

<style>
/* 每段一页：min-height 由 JS 写成 --pw-home-page（滚动容器实测高度）；
   翻页不用 CSS scroll-snap —— 吸附只按「离哪个边界近」决定，下一段标题刚出现时往往还差半屏，
   所以改成脚本监听标题进视口再整段切过去（见 maybePaging）。 */
.home-page {
  min-height: var(--pw-home-page, 100svh);
}

/* 简介里的行内 Markdown 链接：全局 base 把 a 抹成 color:inherit + 无下划线，
   不补样式的话渲染出来的链接与周围正文同色同饰、等于隐形。 */
.home-intro a { color: var(--c-primary); font-weight: 600; }
.home-intro a:hover { text-decoration: underline; }
</style>
