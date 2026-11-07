<script setup lang="ts">
/** 页面进度刻度尺（右缘竖向 ruler，形态参考 getartcraft.com 的 page position 刻度条）
 *  - 刻度随内容一起滚动：每 1% 一条短线，每 5% 一条长线并带百分比数字
 *  - 当前位置：一条发光主色横线 + 里程表式（逐位滚动）百分比读数
 *  - 点击/拖拽刻度尺可直接跳转定位
 *  - 右缘目录：全部标题自上而下排在右上角，当前项高亮；
 *    当前项下方一条横向高亮线，按「本章标题 → 下一标题」的滚动进度横移，不做文字飞行
 *  站点滚动发生在 main 内部，所以监听容器而非 window。 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { setAnchorHash } from '@/utils/link'

const props = withDefaults(defineProps<{
  /** 滚动容器；不传则自动找 main，再退回文档根 */
  target?: HTMLElement | null
}>(), { target: null })

const root = ref<HTMLElement | null>(null)
const scrollTop = ref(0)
const scrollHeight = ref(0)
const viewH = ref(0)
const pct = ref(0)
const ready = ref(false)

const TICKS = Array.from({ length: 101 }, (_, i) => i)
const digits = computed(() => String(Math.round(pct.value)).split('').map(Number))
const rounded = computed(() => Math.round(pct.value))
/** 刻度标签离光标线不足一行的像素距离时让位给读数（按像素判定，长短文章一致） */
const nearCursor = (t: number) => Math.abs(((t - pct.value) / 100) * scrollHeight.value) < 16

let scroller: HTMLElement | null = null
let ro: ResizeObserver | null = null
let roContent: ResizeObserver | null = null
let raf = 0
let idle = 0
let dragging = false

/** 右缘目录 + 当前项横向高亮线
 *  已读标题堆在上方、未读堆在下方，当前标题落在两堆之间的空档；
 *  空档里只画一条横向高亮线，按当前章节的滚动进度横移。 */
interface Head { id: string; top: number; text: string }
const heads = ref<Head[]>([])
const activeIdx = ref(-1)
/** 当前章节在「本章标题 → 下一标题」之间的滚动进度（0 → 1） */
const sectionPct = ref(0)
/** 只有文章页才展示目录；首页/列表页只有一条 h1，浮在内容上纯属噪声 */
const hasArticle = ref(false)

const GAP = 22
const TOP_PAD = 96
const BOT_PAD = 64
/** 目录显示全部标题；条目间距按数量自适应压缩（最短 10px），中间留出当前项的空间 */
const MIN_GAP = 10

/** 全部标题：不再区分已读 / 未读，自上而下排在右上角 */
const tocList = computed(() => heads.value.map((h, i) => ({ i, text: h.text })))
/** 间距随条目数自适应：尽量铺满右侧高度，最少 10px */
const tocGap = computed(() => {
  const n = tocList.value.length
  if (n < 2) return GAP
  const space = Math.max(0, viewH.value - TOP_PAD - BOT_PAD)
  return Math.max(MIN_GAP, Math.min(GAP, space / (n - 1)))
})
const tocY = (i: number) => TOP_PAD + i * tocGap.value

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v)


/** 目录项点击跳转（右缘列表就是文章目录） */
function jumpTo(i: number) {
  // SSG 水合/字体加载后缓存的 top 可能过期；点击时按当前 DOM 重新量一次
  remeasure()
  const h = heads.value[i]
  if (!h || !scroller) return
  setAnchorHash(h.id)
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const behavior = reduced ? 'instant' : 'smooth'
  const el = h.id ? document.getElementById(h.id) : null
  if (el) el.scrollIntoView({ behavior, block: 'start' })
  else scroller.scrollTo({ top: Math.max(0, h.top - 80), behavior })
}

/** 只读 scrollTop：滚动中每帧调用，避免反复触发重排 */
function paint() {
  const el = scroller
  if (!el) return
  scrollTop.value = el.scrollTop
  const max = scrollHeight.value - viewH.value
  pct.value = max > 0 ? Math.min(100, Math.max(0, (el.scrollTop / max) * 100)) : 0
  // 当前章节：视口顶部 80px 处作为探测线，取它上方最近的标题
  // （用固定像素而不是视口百分比：页面刚打开时 h1 一定在探测线之上，标题不会一上来就跳到第二节）
  const probe = el.scrollTop + 80
  let idx = -1
  for (let i = 0; i < heads.value.length; i++) if (heads.value[i].top <= probe) idx = i
  activeIdx.value = idx

  const h = heads.value[idx]
  if (h) {
    const next = heads.value[idx + 1]
    const span = Math.max(1, (next ? next.top : scrollHeight.value) - h.top)
    sectionPct.value = clamp01((probe - h.top) / span)
  } else {
    sectionPct.value = 0
  }
}

/** 收集标题：文章页取正文 h1/h2/h3 做章节切换；列表页只取页面 h1，避免卡片标题乱跳 */
function collectHeads(el: HTMLElement) {
  const base = el.getBoundingClientRect().top - el.scrollTop
  const article = el.querySelector('article')
  hasArticle.value = !!article
  const nodes = article
    ? [...article.querySelectorAll<HTMLElement>('h1, h2, h3')]
    : [...el.querySelectorAll<HTMLElement>('h1')].slice(0, 1)
  heads.value = nodes
    .filter((h) => h.offsetParent !== null)
    .map((h) => ({
      id: h.id,
      top: h.getBoundingClientRect().top - base,
      text: (h.textContent ?? '').trim().replace(/\s+/g, ' '),
    }))
    .filter((h) => h.text)
}

/** 读布局尺寸：只在挂载、尺寸变化、滚动结束后调用 */
function remeasure() {
  const el = scroller
  if (!el) return
  scrollHeight.value = el.scrollHeight
  viewH.value = el.clientHeight
  ready.value = scrollHeight.value - viewH.value > 80
  collectHeads(el)
  paint()
}

function onScroll() {
  if (raf) return
  raf = requestAnimationFrame(() => { raf = 0; paint() })
  // 滚动停下来后再校准一次总高（图片懒加载会改变内容高度）
  clearTimeout(idle)
  idle = window.setTimeout(remeasure, 160)
}

function ratioToScroll(clientY: number) {
  const el = scroller
  const box = root.value
  if (!el || !box) return
  const r = box.getBoundingClientRect()
  const ratio = Math.min(1, Math.max(0, (clientY - r.top) / r.height))
  el.scrollTop = ratio * (el.scrollHeight - el.clientHeight)
}

function onPointerDown(e: PointerEvent) {
  if (e.button !== 0) return
  dragging = true
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  ratioToScroll(e.clientY)
}
function onPointerMove(e: PointerEvent) {
  if (dragging) ratioToScroll(e.clientY)
}
function onPointerUp(e: PointerEvent) {
  dragging = false
  ;(e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId)
}

function bind() {
  const el = props.target ?? document.querySelector<HTMLElement>('main') ?? document.documentElement
  scroller = el
  el.addEventListener('scroll', onScroll, { passive: true })
  ro = new ResizeObserver(remeasure)
  ro.observe(el)
  // 内容容器高度变化（路由切换、图片加载）也要重新量
  const inner = el.firstElementChild
  if (inner) {
    roContent = new ResizeObserver(remeasure)
    roContent.observe(inner)
  }
  remeasure()
}

function refresh() {
  remeasure()
}

onMounted(bind)
onBeforeUnmount(() => {
  scroller?.removeEventListener('scroll', onScroll)
  ro?.disconnect()
  roContent?.disconnect()
  clearTimeout(idle)
  if (raf) cancelAnimationFrame(raf)
})

defineExpose({ refresh })
</script>

<template>
  <div
    v-show="ready"
    ref="root"
    class="ruler"
    role="scrollbar"
    aria-controls="main"
    aria-orientation="vertical"
    aria-valuemin="0"
    aria-valuemax="100"
    :aria-valuenow="rounded"
    aria-label="页面进度"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
  >
    <!-- 右缘毛玻璃：向左渐隐，只压住最边上一条 -->
    <div class="ruler__veil" aria-hidden="true" />

    <!-- 刻度轨道：高度=文档总高，随滚动上移，刻度因此“路过”视口 -->
    <div class="ruler__track" :style="{ height: `${scrollHeight}px`, transform: `translate3d(0, ${-scrollTop}px, 0)` }" aria-hidden="true">
      <div v-for="t in TICKS" :key="t" class="ruler__tick-row" :style="{ top: `${(t / 100) * scrollHeight}px` }">
        <span class="ruler__tick" :class="{ 'ruler__tick--major': t % 5 === 0 }" />
        <span v-if="t % 5 === 0" class="ruler__tick-label" :class="{ 'is-muted': nearCursor(t) }">{{ t }}</span>
      </div>
    </div>

    <!-- 当前位置：发光横线 + 里程表读数 -->
    <div class="ruler__cursor" :class="{ 'is-flip': pct > 92 }" :style="{ top: `${(pct / 100) * (viewH || 0)}px` }" aria-hidden="true">
      <span class="ruler__cursor-line" />
      <span class="ruler__readout">
        <span class="ruler-digits">
          <span v-for="(d, i) in digits" :key="i" class="ruler-digit-col" :style="{ transform: `translateY(-${d}em)` }">
            <span v-for="n in 10" :key="n">{{ n - 1 }}</span>
          </span>
        </span><span class="ruler__pct-sign">%</span>
      </span>
    </div>
  </div>

  <!-- 右缘目录：全部标题自上而下排在右上角；当前项下方一条横向进度线 -->
  <div v-show="ready && hasArticle && heads.length" class="ruler__toc" aria-hidden="true">
    <div
      v-for="it in tocList"
      :key="it.i"
      class="ruler__toc-item"
      :class="{ 'is-current': it.i === activeIdx }"
      :style="{ top: `${tocY(it.i)}px`, lineHeight: `${tocGap}px` }"
      @click="jumpTo(it.i)"
    >
      <span class="ruler__toc-text">{{ it.text }}</span>
      <span v-if="it.i === activeIdx" class="ruler__current-bar" aria-hidden="true">
        <i :style="{ left: `${sectionPct * 100}%` }" />
      </span>
    </div>
  </div>
</template>

<style scoped>
.ruler {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 30; /* 低于 header(z-40)，顶部不会被导航压住点击 */
  width: 60px;
  overflow: hidden;
  cursor: crosshair;
  touch-action: none;
}

.ruler__veil {
  position: absolute;
  inset: 0;
  background-color: color-mix(in srgb, var(--c-bg) 55%, transparent);
  backdrop-filter: blur(9px);
  -webkit-backdrop-filter: blur(9px);
  mask-image: linear-gradient(
    to left,
    #000 40%,
    rgb(0 0 0 / 0.745) 47.5%,
    rgb(0 0 0 / 0.53) 55%,
    rgb(0 0 0 / 0.357) 62.5%,
    rgb(0 0 0 / 0.22) 70%,
    rgb(0 0 0 / 0.118) 77.5%,
    rgb(0 0 0 / 0.047) 85%,
    rgb(0 0 0 / 0.01) 92.5%,
    transparent 100%
  );
  -webkit-mask-image: linear-gradient(
    to left,
    #000 40%,
    rgb(0 0 0 / 0.745) 47.5%,
    rgb(0 0 0 / 0.53) 55%,
    rgb(0 0 0 / 0.357) 62.5%,
    rgb(0 0 0 / 0.22) 70%,
    rgb(0 0 0 / 0.118) 77.5%,
    rgb(0 0 0 / 0.047) 85%,
    rgb(0 0 0 / 0.01) 92.5%,
    transparent 100%
  );
}

.ruler__track {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  will-change: transform;
}

.ruler__tick-row {
  position: absolute;
  left: 0;
  right: 0;
  height: 0;
}

.ruler__tick {
  position: absolute;
  right: 0;
  top: 0;
  display: block;
  width: 10px;
  height: 1px;
  background: var(--c-text);
  opacity: 0.4;
}

.ruler__tick--major {
  width: 20px;
  opacity: 0.8;
}

.ruler__tick-label {
  position: absolute;
  right: 24px;
  top: 0;
  transform: translateY(-50%);
  font-family: ui-monospace, SFMono-Regular, 'JetBrains Mono', Menlo, monospace;
  font-size: 9px;
  line-height: 1;
  letter-spacing: 0.08em;
  color: var(--c-text);
  opacity: 0.5;
  transition: opacity 0.18s ease;
}

/* 光标停在某个整 5% 上时，读数会占住同一个位置，把那条刻度标签让出来 */
.ruler__tick-label.is-muted {
  opacity: 0;
}

.ruler__cursor {
  position: absolute;
  left: 0;
  right: 0;
  height: 0;
  pointer-events: none;
  transition: top 0.08s linear;
}

.ruler__cursor-line {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  height: 1px;
  background: var(--c-primary);
  box-shadow: 0 0 6px var(--c-primary);
}

.ruler__readout {
  position: absolute;
  right: 2px;
  top: 4px;
  display: inline-flex;
  align-items: flex-start;
  white-space: nowrap;
  font-family: ui-monospace, SFMono-Regular, 'JetBrains Mono', Menlo, monospace;
  font-size: 9px;
  line-height: 1;
  letter-spacing: 0.08em;
  color: var(--c-primary);
}

.ruler-digits {
  display: inline-flex;
  height: 1em;
  line-height: 1;
  overflow: hidden;
}

/* 快到底时读数翻到线上方，否则会被视口下沿裁掉 */
.ruler__cursor.is-flip .ruler__readout {
  top: auto;
  bottom: 4px;
}

.ruler-digit-col {
  display: flex;
  flex-direction: column;
  transition: transform 0.28s cubic-bezier(0.2, 0.9, 0.2, 1);
}

.ruler-digit-col > span {
  display: block;
  height: 1em;
}

.ruler__pct-sign {
  margin-left: 2px;
}

/* ── 右缘目录 ── */
.ruler__toc {
  position: fixed;
  top: 0;
  right: 76px;
  bottom: 0;
  z-index: 30;
  width: min(300px, 40vw);
  pointer-events: none;
}

.ruler__toc-item {
  position: absolute;
  right: 0;
  max-width: 100%;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  text-align: right;
  font-size: 11px;
  line-height: 22px;
  color: var(--c-text);
  opacity: 0.45;
  /* 目录项可点击跳转（列表容器本身 pointer-events: none） */
  pointer-events: auto;
  cursor: pointer;
  /* 间距是自适应的，条目数变化时要「滑」到新槽位而不是瞬移 */
  transition:
    opacity 0.18s ease,
    color 0.18s ease,
    top 0.26s cubic-bezier(0.2, 0.9, 0.2, 1),
    line-height 0.26s cubic-bezier(0.2, 0.9, 0.2, 1);
  /* 背景是正文/毛玻璃，给文字一层同底色柔光保证可读 */
  text-shadow: 0 1px 14px color-mix(in srgb, var(--c-bg) 85%, transparent);
}

.ruler__toc-text {
  display: block;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.ruler__toc-item:hover {
  color: var(--c-primary);
  opacity: 1;
}

/* 1280 以下正文是满宽的，右缘列表会压到文字上，只保留刻度尺 */
@media (max-width: 1279px) {
  .ruler__toc {
    display: none;
  }
}

/* ── 当前项：横向高亮线 ── */
.ruler__toc-item.is-current {
  overflow: visible;
  opacity: 1;
  color: var(--c-primary);
  font-weight: 600;
}

.ruler__current-bar {
  position: absolute;
  left: 0;
  right: 0;
  bottom: -3px;
  height: 1px;
  background: color-mix(in srgb, var(--c-text) 16%, transparent);
}

.ruler__current-bar i {
  position: absolute;
  top: -0.5px;
  width: 16px;
  height: 2px;
  border-radius: 1px;
  background: var(--c-primary);
  box-shadow: 0 0 8px var(--c-primary);
  transform: translateX(-50%);
  transition: left 0.08s linear;
}

/* 窄屏没有余量，直接不显示 */
@media (max-width: 767px) {
  .ruler,
  .ruler__toc {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ruler-digit-col,
  .ruler__cursor,
  .ruler__current-bar i {
    transition: none;
  }
}
</style>
