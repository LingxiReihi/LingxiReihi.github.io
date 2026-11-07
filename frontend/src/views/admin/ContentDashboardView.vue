<script setup lang="ts">
import {
  BarChart, LineChart,
} from 'echarts/charts'
import {
  GridComponent, TooltipComponent,
} from 'echarts/components'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import {
  NButton, NDropdown, NImage, NPopconfirm, NSpin, NTag, useMessage,
} from 'naive-ui'
import VChart from 'vue-echarts'

import { useChartTheme } from '@/composables/useChartTheme'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { adminCommentsApi, adminContentsApi, adminStatsApi } from '@/api'
import type { AdminContent } from '@/api'
import type { AdminComment } from '@/api/types'
import { formatDateTime } from '@/utils/format'

const ct = useChartTheme()
import { buildMarkdown, copyText, downloadText, markdownFilename } from '@/utils/markdown'

use([CanvasRenderer, LineChart, BarChart, GridComponent, TooltipComponent])

const route = useRoute()
const router = useRouter()
const message = useMessage()
const id = Number(route.params.id)

type Dash = AdminContent & { comments: { pending: number; approved: number; rejected: number; total: number } }
const dash = ref<Dash | null>(null)
const loading = ref(true)
const range = ref<7 | 30>(7)

const days = ref<{ day: string; pv: number; uv: number }[]>([])
const sources = ref<{ referrer: string; pv: number }[]>([])

// 评论
const comments = ref<AdminComment[]>([])
const cTotal = ref(0)
const cPage = ref(1)
const cSize = 10
const cStatus = ref<string>('pending')
const cLoading = ref(false)
const COMMENT_PILLS = [
  { value: 'pending', label: '待审核' },
  { value: 'approved', label: '已通过' },
  { value: 'rejected', label: '已拒绝' },
  { value: '', label: '全部' },
]
const STATUS_META: Record<string, { label: string; type: 'warning' | 'success' | 'error' | 'default' }> = {
  pending: { label: '待审', type: 'warning' },
  approved: { label: '通过', type: 'success' },
  rejected: { label: '拒绝', type: 'error' },
}

async function loadDash() {
  loading.value = true
  try {
    dash.value = await adminContentsApi.dashboard(id)
    const d = await adminStatsApi.contentDrill(id)
    days.value = d.days as { day: string; pv: number; uv: number }[]
    sources.value = d.sources as { referrer: string; pv: number }[]
  } catch (e: any) {
    message.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(() => { loadDash(); loadComments() })

async function loadComments() {
  cLoading.value = true
  try {
    const d = await adminCommentsApi.list({
      content_id: id, status: cStatus.value || undefined, page: cPage.value, page_size: cSize,
    })
    comments.value = d.items
    cTotal.value = d.total
  } catch (e: any) {
    message.error(e?.message || '评论加载失败')
  } finally {
    cLoading.value = false
  }
}
function switchCommentStatus(s: string) { cStatus.value = s; cPage.value = 1; loadComments() }

async function moderate(cid: number, st: string) {
  try {
    await adminCommentsApi.moderate([cid], st)
    await Promise.all([loadComments(), loadDash()])
  } catch (e: any) { message.error(e?.message || '操作失败') }
}
async function removeComment(cid: number) {
  try {
    await adminCommentsApi.remove(cid)
    await Promise.all([loadComments(), loadDash()])
  } catch (e: any) { message.error(e?.message || '删除失败') }
}

async function setStatus(st: string) {
  try {
    await adminContentsApi.setStatus(id, st)
    message.success(st === 'published' ? '已发布' : '已下架')
    await loadDash()
  } catch (e: any) { message.error(e?.message || '操作失败') }
}

// ── 导出 Markdown ──
// 正文用 dashboard 已返回的 body_md 原文，不重新请求；front-matter 便于二次导入
const MD_MENU = [
  { label: '下载 .md（含元信息）', key: 'full' },
  { label: '仅下载正文', key: 'body' },
  { label: '复制 Markdown', key: 'copy' },
]

async function exportMarkdown(mode: 'full' | 'body' | 'copy') {
  const c = dash.value
  if (!c) { message.warning('内容尚未加载完成'); return }
  const text = buildMarkdown(c, { frontMatter: mode !== 'body' })
  if (mode === 'copy') {
    try {
      await copyText(text)
      message.success('Markdown 已复制到剪贴板')
    } catch { message.error('复制失败，请改用下载') }
    return
  }
  const filename = markdownFilename(c)
  downloadText(filename, text)
  message.success(`已导出 ${filename}`)
}

/** 下拉菜单 select 事件的 key 是 string | number，收窄到导出模式 */
function onMdSelect(key: string | number) {
  const mode = String(key)
  if (mode === 'full' || mode === 'body' || mode === 'copy') exportMarkdown(mode)
}

const trendOption = computed(() => {
  const slice = days.value.slice(-range.value)
  return {
    grid: { left: 44, right: 16, top: 32, bottom: 24 },
    tooltip: { trigger: 'axis', ...ct.tooltip.value },
    legend: { data: ['PV', 'UV'], top: 0, icon: 'rect', itemWidth: 8, itemHeight: 8, textStyle: ct.legendText.value },
    xAxis: {
      type: 'category', data: slice.map((d) => d.day.slice(4, 6) + '-' + d.day.slice(6, 8)),
      axisLine: ct.axisLine.value, axisTick: { show: false }, axisLabel: ct.axisLabel.value,
    },
    yAxis: { type: 'value', minInterval: 1, splitLine: ct.splitLine.value, axisLabel: ct.axisLabel.value },
    series: [
      ct.lineSeries('PV', slice.map((d) => d.pv), 0, true),
      ct.lineSeries('UV', slice.map((d) => d.uv), 1),
    ],
  }
})

const TYPE_LABEL: Record<string, string> = { article: '文章', model: '模型', chat: '杂谈' }
const STATUS_LABEL: Record<string, { label: string; type: 'default' | 'success' | 'warning' }> = {
  draft: { label: '草稿', type: 'default' },
  published: { label: '已发布', type: 'success' },
  archived: { label: '已下架', type: 'warning' },
}
const frontPath = computed(() => {
  const c = dash.value
  if (!c) return ''
  return c.type === 'article' ? `/blog/${c.slug}` : c.type === 'model' ? `/models/${c.slug}` : `/chats/${c.id}`
})
</script>

<template>
  <div>
    <div class="mb-4 flex flex-wrap items-center gap-3">
      <button class="text-sm text-ink-3 hover:text-brand" @click="router.push('/admin/content')">← 列表</button>
      <h1 class="text-xl font-bold">内容仪表盘</h1>
      <div class="ml-auto flex items-center gap-2">
        <div class="flex items-center">
          <n-button size="small" :disabled="!dash" @click="exportMarkdown('full')">⬇ 下载 MD</n-button>
          <n-dropdown trigger="click" :options="MD_MENU" :disabled="!dash" @select="onMdSelect">
            <n-button size="small" quaternary :disabled="!dash" class="!px-1.5" title="更多导出方式">▾</n-button>
          </n-dropdown>
        </div>
        <n-button size="small" @click="router.push(`/admin/content/${id}/edit`)">编辑</n-button>
        <n-button v-if="dash?.status === 'published'" size="small" @click="setStatus('archived')">下架</n-button>
        <n-button v-else size="small" type="primary" @click="setStatus('published')">发布</n-button>
        <n-button v-if="dash?.status === 'published'" size="small" tag="a" :href="frontPath" target="_blank">查看前台 ↗</n-button>
      </div>
    </div>

    <n-spin :show="loading">
      <div v-if="dash" class="mb-5 flex flex-wrap items-center gap-3  border border-line bg-surface p-4">
        <n-image v-if="dash.cover" :src="dash.cover" width="72" height="48" :preview-disabled="true" object-fit="cover" />
        <div class="min-w-0">
          <p class="truncate text-base font-semibold">{{ dash.title }}</p>
          <p class="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-3">
            <n-tag size="tiny" :bordered="false">{{ TYPE_LABEL[dash.type] ?? dash.type }}</n-tag>
            <n-tag size="tiny" :bordered="false" :type="STATUS_LABEL[dash.status]?.type ?? 'default'">{{ STATUS_LABEL[dash.status]?.label ?? dash.status }}</n-tag>
            <span v-if="dash.slug">/{{ dash.slug }}</span>
            <span>· 更新于 {{ formatDateTime(dash.updated_at) }}</span>
          </p>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <div class=" border border-line bg-surface p-5">
          <p class="text-xs text-ink-3">累计浏览</p>
          <p class="mt-2 text-3xl font-bold" style="color: var(--c-primary)">{{ dash?.view_count ?? 0 }}</p>
        </div>
        <div class=" border border-line bg-surface p-5">
          <p class="text-xs text-ink-3">点赞</p>
          <p class="mt-2 text-3xl font-bold" style="color: var(--c-primary)">{{ dash?.likes ?? 0 }}</p>
        </div>
        <div class=" border border-line bg-surface p-5">
          <p class="text-xs text-ink-3">评论总数</p>
          <p class="mt-2 text-3xl font-bold" style="color: var(--c-primary)">{{ dash?.comments.total ?? 0 }}</p>
        </div>
        <div class=" border border-line bg-surface p-5">
          <p class="text-xs text-ink-3">待审评论</p>
          <p class="mt-2 text-3xl font-bold" :class="dash?.comments.pending ? 'text-warning' : ''" :style="dash?.comments.pending ? '' : 'color: var(--c-primary)'">{{ dash?.comments.pending ?? 0 }}</p>
        </div>
      </div>

      <div class="mt-5 grid gap-5 xl:grid-cols-[2fr_1fr]">
        <div class=" border border-line bg-surface p-4">
          <div class="mb-2 flex items-center gap-3">
            <p class="text-sm font-medium text-ink-2">浏览趋势</p>
            <div class="ml-auto flex gap-1">
              <button
                v-for="r in ([7, 30] as const)" :key="r"
                class=" border px-2.5 py-0.5 text-xs"
                :class="range === r ? 'border-brand text-brand' : 'border-line text-ink-3 hover:text-ink'"
                @click="range = r"
              >近 {{ r }} 天</button>
            </div>
          </div>
          <v-chart v-if="days.length" :option="trendOption" autoresize style="height: 260px" />
          <p v-else-if="!loading" class="py-16 text-center text-sm text-ink-3">暂无浏览数据</p>
        </div>
        <div class=" border border-line bg-surface p-4">
          <p class="mb-2 text-sm font-medium text-ink-2">来源 Top</p>
          <ul v-if="sources.length" class="space-y-2 text-sm">
            <li v-for="(s, i) in sources.slice(0, 8)" :key="i" class="flex items-center justify-between gap-2">
              <span class="truncate text-ink-2" :title="s.referrer || '直接访问'">{{ s.referrer || '直接访问' }}</span>
              <span class="shrink-0 text-ink-3">{{ s.pv }}</span>
            </li>
          </ul>
          <p v-else-if="!loading" class="py-16 text-center text-sm text-ink-3">暂无来源数据</p>
        </div>
      </div>

      <!-- 评论管理 -->
      <div class="mt-5  border border-line bg-surface p-4">
        <div class="mb-3 flex flex-wrap items-center gap-2">
          <p class="text-sm font-medium text-ink-2">评论（{{ cTotal }}）</p>
          <div class="ml-auto flex flex-wrap gap-1">
            <button
              v-for="p in COMMENT_PILLS" :key="p.value"
              class="rounded-full border px-3 py-1 text-xs transition-colors"
              :class="cStatus === p.value ? 'border-brand bg-brand/10 text-brand' : 'border-line text-ink-3 hover:border-brand/50'"
              @click="switchCommentStatus(p.value)"
            >
              {{ p.label }}<template v-if="p.value === 'pending' && dash?.comments.pending"> ({{ dash.comments.pending }})</template>
            </button>
          </div>
        </div>
        <n-spin :show="cLoading">
          <ul v-if="comments.length" class="divide-y divide-line">
            <li v-for="c in comments" :key="c.id" class="flex items-start gap-3 py-3">
              <n-image :src="c.avatar" width="32" height="32" class="!rounded-full shrink-0" :preview-disabled="true" object-fit="cover" />
              <div class="min-w-0 flex-1">
                <p class="text-sm">
                  <span class="font-medium">{{ c.nickname }}</span>
                  <span class="ml-2 text-xs text-ink-3">{{ c.email }} · {{ formatDateTime(c.created_at) }}</span>
                  <n-tag class="ml-2" size="tiny" :bordered="false" :type="STATUS_META[c.status]?.type ?? 'default'">{{ STATUS_META[c.status]?.label ?? c.status }}</n-tag>
                </p>
                <p class="mt-1 whitespace-pre-wrap break-words text-sm text-ink-2">{{ c.body }}</p>
              </div>
              <div class="flex shrink-0 gap-1">
                <n-button v-if="c.status !== 'approved'" size="tiny" type="primary" @click="moderate(c.id, 'approved')">通过</n-button>
                <n-button v-if="c.status !== 'rejected'" size="tiny" @click="moderate(c.id, 'rejected')">拒绝</n-button>
                <n-popconfirm @positive-click="removeComment(c.id)">
                  <template #trigger><n-button size="tiny" quaternary type="error">删除</n-button></template>
                  删除该评论？
                </n-popconfirm>
              </div>
            </li>
          </ul>
          <p v-else-if="!cLoading" class="py-10 text-center text-sm text-ink-3">该筛选下暂无评论</p>
        </n-spin>
        <div v-if="cTotal > cSize" class="mt-3 flex justify-center gap-2 text-sm">
          <n-button size="tiny" :disabled="cPage <= 1" @click="cPage--; loadComments()">上一页</n-button>
          <span class="py-1 text-ink-3">{{ cPage }} / {{ Math.ceil(cTotal / cSize) }}</span>
          <n-button size="tiny" :disabled="cPage >= Math.ceil(cTotal / cSize)" @click="cPage++; loadComments()">下一页</n-button>
        </div>
      </div>
    </n-spin>
  </div>
</template>
