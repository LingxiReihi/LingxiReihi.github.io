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
  NButton, NDataTable, NModal,
  useMessage,
} from 'naive-ui'
import VChart from 'vue-echarts'

import { useChartTheme } from '@/composables/useChartTheme'
import { computed, h, onMounted, ref } from 'vue'
import type { DataTableColumns } from 'naive-ui'
import { useRouter } from 'vue-router'

import { adminStatsApi } from '@/api'
import type { StatsOverview } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { formatSize } from '@/utils/format'

use([CanvasRenderer, LineChart, BarChart, GridComponent, TooltipComponent])

const ct = useChartTheme()

const auth = useAuthStore()
const message = useMessage()
const router = useRouter()
const loading = ref(true)
const range = ref<'7d' | '30d' | '90d'>('7d')
const overview = ref<StatsOverview | null>(null)
const trend = ref<{ day: string; pv: number; uv: number }[]>([])
const top = ref<Record<string, unknown>[]>([])
const sources = ref<{ items: { referrer: string; pv: number }[]; direct: number; search: number; social: number; other: number } | null>(null)
const drill = ref<{ id: number; title: string; days: { day: string; pv: number; uv: number }[] } | null>(null)
const drillLoading = ref(false)

const growth = computed(() => {
  if (!overview.value) return null
  const { today, yesterday } = overview.value
  if (!yesterday.pv) return null
  return Math.round(((today.pv - yesterday.pv) / yesterday.pv) * 100)
})

async function loadAll() {
  // 统计看板是权限点 stats:view；无权的普通管理员不进后台请求，避免连报 4 个 403
  if (!auth.can('stats:view')) {
    loading.value = false
    message.info('你没有数据看板权限，工作台已跳过统计模块')
    return
  }
  loading.value = true
  const days = range.value === '7d' ? 7 : range.value === '30d' ? 30 : 90
  // trend 后端缺省只回 7 天，须显式传 UTC 起止，否则 30d/90d 切换无效果
  const ymd = (d: Date) => d.toISOString().slice(0, 10).replaceAll('-', '')
  const end = new Date()
  const start = new Date(end.getTime() - (days - 1) * 86400_000)
  try {
    const [ov, tr, tc, sc] = await Promise.all([
      adminStatsApi.overview(),
      adminStatsApi.trend(ymd(start), ymd(end)),
      adminStatsApi.topContent(range.value, 10),
      adminStatsApi.sources(range.value),
    ])
    overview.value = ov
    trend.value = tr.days.slice(-days)
    top.value = tc.items
    sources.value = sc
  } catch (e: any) {
    message.error(e?.message || '统计数据加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(loadAll)

const trendOption = computed(() => ({
  grid: { left: 44, right: 16, top: 32, bottom: 24 },
  tooltip: { trigger: 'axis', ...ct.tooltip.value },
  legend: { data: ['PV', 'UV'], top: 0, icon: 'rect', itemWidth: 8, itemHeight: 8, textStyle: ct.legendText.value },
  xAxis: {
    type: 'category', data: trend.value.map((d) => d.day.slice(4, 6) + '-' + d.day.slice(6, 8)),
    axisLine: ct.axisLine.value, axisTick: { show: false }, axisLabel: ct.axisLabel.value,
  },
  yAxis: { type: 'value', splitLine: ct.splitLine.value, axisLabel: ct.axisLabel.value },
  series: [
    ct.lineSeries('PV', trend.value.map((d) => d.pv), 0, true),
    ct.lineSeries('UV', trend.value.map((d) => d.uv), 1),
  ],
}))

const sourceOption = computed(() => {
  if (!sources.value) return {}
  return {
    grid: { left: 8, right: 8, top: 30, bottom: 24 },
    tooltip: { trigger: 'item', ...ct.tooltip.value },
    xAxis: {
      type: 'category', data: ['直接', '搜索', '社交', '其他'],
      axisLabel: ct.axisLabel.value, axisLine: { show: false }, axisTick: { show: false },
    },
    yAxis: { type: 'value', show: false },
    series: [{
      type: 'bar', barWidth: 18,
      data: [sources.value.direct, sources.value.search, sources.value.social, sources.value.other],
      itemStyle: { color: ct.palette.value[0] },
      label: { show: true, position: 'top', color: ct.c.value.text2, fontSize: 10 },
    }],
  }
})

async function exportCsv() {
  try {
    const { http } = await import('@/api/http')
    const r = await http.get('/admin/stats/export', { responseType: 'text' })
    const blob = new Blob([r.data as string], { type: 'text/csv;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `stats-${range.value}.csv`
    a.click()
    URL.revokeObjectURL(a.href)
  } catch { message.error('导出失败') }
}

async function openDrill(row: Record<string, unknown>) {
  drillLoading.value = true
  drill.value = { id: Number(row.content_id), title: String(row.title), days: [] }
  try {
    const d = await adminStatsApi.contentDrill(Number(row.content_id))
    drill.value = { ...drill.value, days: d.days as { day: string; pv: number; uv: number }[] }
  } catch (e: any) {
    message.error(e?.message || '下钻失败')
  } finally {
    drillLoading.value = false
  }
}

// 内容列必须有宽度：其余四列固定占 TOP_FIXED_W，卡片在窄屏只有 ~330px，
// 不给宽度的话这一列会被压到只剩首字母（"N." / "P."）。设了宽就靠 scroll-x 横向滑。
const TOP_TITLE_W = 240
const TOP_FIXED_W = 70 + 70 + 70 + 60
const topColumns = computed<DataTableColumns<Record<string, unknown>>>(() => [
  {
    title: '内容', key: 'title', width: TOP_TITLE_W, ellipsis: { tooltip: true },
    // 与内容列表同一套：标题点进该篇的内容仪表盘；行尾「下钻」仍是本页弹窗，两者用途不同
    render: (row) => h('a', {
      class: 'cursor-pointer hover:text-brand',
      href: `/admin/content/${Number(row.content_id)}/dashboard`,
      onClick: (e: MouseEvent) => {
        e.preventDefault()
        router.push(`/admin/content/${Number(row.content_id)}/dashboard`)
      },
    }, String(row.title ?? '')),
  },
  { title: '类型', key: 'type', width: 70 },
  { title: 'PV', key: 'pv', width: 70 },
  { title: 'UV', key: 'uv', width: 70 },
  {
    title: '', key: 'go', width: 60,
    render: (row) => h(NButton, { size: 'tiny', text: true, type: 'primary', onClick: () => openDrill(row) }, () => '下钻'),
  },
])

const cards = computed(() => {
  const o = overview.value
  return [
    { label: '今日 PV', value: o ? String(o.today.pv) : '—', sub: o ? `昨日 ${o.yesterday.pv}${growth.value !== null ? ` · ${growth.value >= 0 ? '+' : ''}${growth.value}%` : ''}` : '' },
    { label: '今日 UV', value: o ? String(o.today.uv) : '—', sub: o ? `昨日 ${o.yesterday.uv}` : '' },
    { label: '已发布内容', value: o ? `${(o.total_published.article ?? 0) + (o.total_published.model ?? 0) + (o.total_published.chat ?? 0)}` : '—', sub: o ? `文章${o.total_published.article ?? 0} · 模型${o.total_published.model ?? 0} · 杂谈${o.total_published.chat ?? 0}` : '' },
    { label: '素材占用', value: o ? formatSize(o.storage_used) : '—', sub: o ? `${o.media_count} 个文件` : '' },
  ]
})
</script>

<template>
  <div>
    <div class="mb-5 flex flex-wrap items-center gap-3">
      <h1 class="text-2xl font-bold">仪表盘</h1>
      <div class="ml-auto flex items-center gap-2">
        <button
          v-for="r in (['7d', '30d', '90d'] as const)" :key="r"
          class=" border px-3 py-1 text-xs"
          :class="range === r ? 'border-brand text-brand' : 'border-line text-ink-3 hover:text-ink'"
          @click="range = r; loadAll()"
        >{{ r }}</button>
        <n-button size="tiny" tertiary @click="loadAll">↻</n-button>
        <n-button size="tiny" tertiary @click="exportCsv">导出 CSV</n-button>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-4 xl:grid-cols-4">
      <div v-for="c in cards" :key="c.label" class=" border border-line bg-surface p-5">
        <p class="text-xs text-ink-3">{{ c.label }}</p>
        <p class="mt-2 text-3xl font-bold" style="color: var(--c-primary)">{{ c.value }}</p>
        <p class="mt-1 text-xs text-ink-3">{{ c.sub }}</p>
      </div>
    </div>

    <div class="mt-5 grid gap-5 xl:grid-cols-[2fr_1fr]">
      <div class=" border border-line bg-surface p-4">
        <p class="mb-2 text-sm font-medium text-ink-2">访问趋势</p>
        <v-chart v-if="!loading" :option="trendOption" autoresize style="height: 280px" />
        <div v-else class="h-[280px]" />
      </div>
      <div class=" border border-line bg-surface p-4">
        <p class="mb-2 text-sm font-medium text-ink-2">来源分布（{{ range }}）</p>
        <v-chart v-if="!loading && sources" :option="sourceOption" autoresize style="height: 280px" />
        <div v-else class="h-[280px]" />
      </div>
    </div>

    <div class="mt-5  border border-line bg-surface p-4">
      <p class="mb-3 text-sm font-medium text-ink-2">热门内容 Top 10（点击行「下钻」）</p>
      <n-data-table
        size="small" :columns="topColumns" :data="top" :loading="loading"
        :scroll-x="TOP_TITLE_W + TOP_FIXED_W"
        :row-key="(r: Record<string, unknown>) => Number(r.content_id)"
      />
      <p v-if="!loading && !top.length" class="py-8 text-center text-sm text-ink-3">
        还没有访问数据 —— 发布内容并分享链接后，这里会亮起来
      </p>
    </div>

    <n-modal :show="!!drill" preset="card"
             :title="`单篇趋势 · ${drill?.title ?? ''}`" style="width: 640px" @update:show="(v: boolean) => { if (!v) drill = null }">
      <v-chart
        v-if="drill && drill.days.length"
        :option="{
          grid: { left: 44, right: 16, top: 20, bottom: 24 },
          tooltip: { trigger: 'axis', ...ct.tooltip.value },
          xAxis: {
            type: 'category', data: drill.days.map(d => d.day.slice(4, 6) + '-' + d.day.slice(6, 8)),
            axisLine: ct.axisLine.value, axisTick: { show: false }, axisLabel: ct.axisLabel.value,
          },
          yAxis: { type: 'value', splitLine: ct.splitLine.value, axisLabel: ct.axisLabel.value },
          series: [ct.lineSeries('PV', drill.days.map(d => d.pv), 0, true)],
        }"
        autoresize style="height: 260px"
      />
      <p v-else class="py-10 text-center text-sm text-ink-3">{{ drillLoading ? '加载中…' : '该篇暂无数据' }}</p>
    </n-modal>
  </div>
</template>
