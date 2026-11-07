<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { AboutMember } from '@/api/types'
import { renderMd } from '@/composables/useMd'

const props = defineProps<{ profile: AboutMember; host?: boolean; highlighted?: boolean }>()

const titleTag = computed(() => (props.host ? 'h1' : 'h2'))
const sectionTag = computed(() => (props.host ? 'h2' : 'h3'))
const bioHtml = computed(() => renderMd(props.profile.bio_md ?? '').html)
const EXP_LABEL = { work: '工作经历', edu: '教育经历', project: '项目经历' } as Record<string, string>

// 默认展开：折叠只是给长页面一个收纳手段，不改变首屏可见内容与预渲染文本
const skillsOpen = ref(true)
const expOpen = ref(true)
const skillsEl = ref<HTMLElement | null>(null)
const expEl = ref<HTMLElement | null>(null)

/**
 * 面板只能按 key 传：模板表达式里的顶层 ref 已被 Vue 解包成布尔值，
 * 把 `skillsOpen` 当参数传进函数再写 `.value` 会当场抛
 * 「Cannot create property value on boolean」，表现为按钮点了没反应。
 */
const PANELS = { skills: { open: skillsOpen, el: skillsEl }, exp: { open: expOpen, el: expEl } }
type PanelKey = keyof typeof PANELS

const running = new WeakMap<HTMLElement, { cancel?: () => void }>()
const watchdogs = new WeakMap<HTMLElement, number>()

function prefersReduced() {
  return typeof window === 'undefined'
    || window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * 折叠用 anime.js 高度过渡；animejs 只在点击时动态 import，不进 SSR 与首包。
 * 终态由 finish() 落定并用 setTimeout 兜底：anime 靠 rAF 推进，而后台标签页里
 * rAF 是冻结的（实测 await requestAnimationFrame 直接挂死），没有兜底的话
 * 按钮点了不会有任何结果。
 */
async function toggle(key: PanelKey) {
  const { open, el } = PANELS[key]
  const next = !open.value
  const node = el.value
  if (!node || prefersReduced()) {
    open.value = next
    return
  }
  let animate: typeof import('animejs')['animate']
  try {
    animate = (await import('animejs')).animate
  } catch {
    open.value = next
    return
  }
  running.get(node)?.cancel?.()
  // 上一次的兜底定时器必须作废，否则连点两次时旧的终态会把新状态盖掉
  const stale = watchdogs.get(node)
  if (stale !== undefined) window.clearTimeout(stale)
  const duration = next ? 260 : 220
  let done = false
  const finish = () => {
    if (done) return
    done = true
    open.value = next
    node.style.height = next ? 'auto' : ''
    node.style.opacity = ''
    node.style.overflow = ''
  }
  node.style.overflow = 'hidden'
  if (next) {
    open.value = true
    await nextTick()
    running.set(node, animate(node, {
      height: [0, node.scrollHeight], opacity: [0, 1], duration, ease: 'outQuad', onComplete: finish,
    }))
  } else {
    // 先把当前高度钉成像素值：inline 还是 auto 时 anime 拿不到确定起点，
    // 实测会退化成「原地不动然后瞬间跳到 0」。
    node.style.height = `${node.getBoundingClientRect().height}px`
    await nextTick()
    running.set(node, animate(node, {
      height: [node.getBoundingClientRect().height, 0], opacity: [1, 0], duration, ease: 'inQuad',
      onComplete: finish,
    }))
  }
  watchdogs.set(node, window.setTimeout(finish, duration + 120))
}

/**
 * 下滑时若大头像被滚出卡片可见区，就把缩略栏钉在卡片顶部。
 * 用哨兵（大卡头之后的一条 1px 标记）+ IntersectionObserver 判定，而不是监听 scroll：
 * sticky 的父级是卡片本身，所以每张卡各自收放，滚到下一张时上一张的条随卡片一起离开。
 * root 取真正滚动的容器（main），否则按视口算会被顶栏那 56px 干扰。
 * 「卡片还在下方没滚到」时也会判成未相交，但那一刻卡片本身不可见，无副作用。
 * 初始态必须是「未缩略」——About 走 vite-ssg 预渲染，SSR 里要输出完整卡头。
 */
const sentinel = ref<HTMLElement | null>(null)
const stuck = ref(false)
let io: IntersectionObserver | null = null

onMounted(() => {
  if (!sentinel.value || typeof IntersectionObserver === 'undefined') return
  const root = sentinel.value.closest('main')
  io = new IntersectionObserver(([e]) => { stuck.value = !e.isIntersecting },
                                { root, threshold: 0 })
  io.observe(sentinel.value)
})
onBeforeUnmount(() => io?.disconnect())

/**
 * 缩略栏的进出也用 anime.js 补间，但**终态交给 class 表达**：anime 只负责过渡，
 * 收尾清掉内联样式交还给 class。这样 rAF 被冻结（后台标签页）或 animejs 加载失败时，
 * 最坏结果只是「没有动画」，不会把栏卡在半隐半现的状态。
 */
const bar = ref<HTMLElement | null>(null)

watch(stuck, async (to) => {
  const node = bar.value
  if (!node || prefersReduced()) return
  let animate: typeof import('animejs')['animate']
  try {
    animate = (await import('animejs')).animate
  } catch {
    return
  }
  running.get(node)?.cancel?.()
  const stale = watchdogs.get(node)
  if (stale !== undefined) window.clearTimeout(stale)
  const duration = to ? 280 : 220
  const settle = () => { node.style.transform = ''; node.style.opacity = '' }
  running.set(node, animate(node, {
    translateY: [to ? '-100%' : '0%', to ? '0%' : '-100%'],
    opacity: to ? [0, 1] : [1, 0],
    duration, ease: to ? 'outQuad' : 'inQuad', onComplete: settle,
  }))
  watchdogs.set(node, window.setTimeout(settle, duration + 120))
})
</script>

<template>
  <section
    :data-author="profile.nickname"
    class="rounded-2xl border border-line bg-glass p-6 backdrop-blur-md transition-shadow duration-500 sm:p-8"
    :class="highlighted ? 'ring-2 ring-brand/70' : ''"
  >
    <header class="flex flex-col items-center gap-4 text-center">
      <img v-if="profile.avatar" :src="profile.avatar" alt="头像" class="h-24 w-24 rounded-full border-2 border-brand/30 object-cover sm:h-28 sm:w-28" />
      <div v-else class="flex h-24 w-24 items-center justify-center rounded-full border-2 border-brand/30 bg-elevated/60 text-5xl sm:h-28 sm:w-28">👾</div>
      <div>
        <component :is="titleTag" class="text-2xl font-bold sm:text-3xl">{{ profile.nickname }}</component>
        <p v-if="profile.signature" class="mt-2 text-ink-2">{{ profile.signature }}</p>
      </div>
    </header>

    <!-- 下滑挡住大卡头时，这条缩略栏钉在卡片可见区顶部；h-0 + absolute 保证它出现/消失不推动正文 -->
    <div ref="sentinel" class="h-px" aria-hidden="true" />
    <div class="sticky top-0 z-10 h-0 overflow-visible" aria-hidden="true">
      <div
        ref="bar"
        class="absolute inset-x-0 top-0 flex -mx-6 items-center gap-2.5 rounded-t-2xl border-b border-line bg-surface/95 px-6 py-2 backdrop-blur-md sm:-mx-8 sm:px-8"
        :class="stuck ? 'translate-y-0 opacity-100' : 'pointer-events-none -translate-y-full opacity-0'"
      >
        <img v-if="profile.avatar" :src="profile.avatar" alt="" class="h-8 w-8 shrink-0 rounded-full border border-line object-cover">
        <div v-else class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-line bg-elevated text-base">👾</div>
        <span class="truncate text-base font-semibold">{{ profile.nickname }}</span>
        <span v-if="profile.signature" class="hidden truncate text-xs text-ink-3 sm:inline">· {{ profile.signature }}</span>
      </div>
    </div>

    <!-- eslint-disable-next-line vue/no-v-html -->
    <div v-if="profile.bio_md" class="prose mt-8" v-html="bioHtml" />

    <section v-if="profile.skills?.length" class="mt-10">
      <button
        type="button" class="flex w-full items-center gap-2 text-left"
        :aria-expanded="skillsOpen" @click="toggle('skills')"
      >
        <component :is="sectionTag" class="text-xl font-bold">技能栈</component>
        <span class="text-xs text-ink-3">{{ skillsOpen ? '收起' : '展开' }}</span>
        <span class="ml-auto inline-block text-xs text-ink-3 transition-transform duration-200" :class="skillsOpen ? 'rotate-90' : ''" aria-hidden="true">▸</span>
      </button>
      <div v-show="skillsOpen" ref="skillsEl" class="mt-4 space-y-4">
        <div v-for="g in profile.skills" :key="g.group">
          <p class="mb-2 text-sm font-medium text-ink-2">{{ g.group }}</p>
          <div class="flex flex-wrap gap-2">
            <span v-for="s in g.items" :key="s" class="rounded-full border border-line bg-elevated/50 px-3 py-1 text-xs text-ink-2">{{ s }}</span>
          </div>
        </div>
      </div>
    </section>

    <section v-if="profile.experience?.length" class="mt-10">
      <button
        type="button" class="flex w-full items-center gap-2 text-left"
        :aria-expanded="expOpen" @click="toggle('exp')"
      >
        <component :is="sectionTag" class="text-xl font-bold">经历</component>
        <span class="text-xs text-ink-3">{{ expOpen ? '收起' : '展开' }}</span>
        <span class="ml-auto inline-block text-xs text-ink-3 transition-transform duration-200" :class="expOpen ? 'rotate-90' : ''" aria-hidden="true">▸</span>
      </button>
      <ol v-show="expOpen" ref="expEl" class="mt-4 space-y-0">
        <li v-for="(e, i) in profile.experience" :key="i" class="relative pb-7 pl-6">
          <span class="absolute left-0 top-1.5 h-2.5 w-2.5 rounded-full bg-brand/60" aria-hidden="true" />
          <span v-if="i !== profile.experience.length - 1" class="absolute bottom-0 left-[4.5px] top-5 w-px bg-line" aria-hidden="true" />
          <p class="text-xs text-ink-3">{{ e.start }}{{ e.end ? ' – ' + e.end : ' – 至今' }} · {{ EXP_LABEL[e.kind] ?? e.kind }}</p>
          <p class="mt-1 font-medium">{{ e.title }}<span class="ml-2 text-sm font-normal text-ink-2">{{ e.org }}</span></p>
          <p v-if="e.desc" class="mt-1 text-sm leading-relaxed text-ink-2">{{ e.desc }}</p>
        </li>
      </ol>
    </section>

    <section v-if="profile.social_links?.length" class="mt-10 text-center">
      <component :is="sectionTag" class="text-xl font-bold">找到我</component>
      <div class="mt-4 flex flex-wrap justify-center gap-3">
        <a
          v-for="s in profile.social_links" :key="s.platform"
          :href="s.url" target="_blank" rel="noopener"
          class="rounded-xl border border-line bg-elevated/50 px-5 py-2.5 text-sm transition-colors hover:border-brand/50 hover:text-brand"
        >{{ s.platform }}</a>
      </div>
    </section>
  </section>
</template>
