<script setup lang="ts">
import {
  NButton, NCheckbox, NDataTable, NTag, useMessage,
} from 'naive-ui'
import { onMounted, ref, h } from 'vue'

import { adminSeoApi } from '@/api'
import { formatDateTime } from '@/utils/format'

const message = useMessage()
const config = ref<{ push_enabled: boolean; api_configured: boolean; rebuild_configured: boolean; rebuild_watcher: boolean; site_url: string } | null>(null)
const logs = ref<Record<string, unknown>[]>([])
const jobs = ref<Record<string, unknown>[]>([])
const busy = ref('')
/** 勾选后忽略去重记录强制重推（默认同一地址只推一次） */
const forcePush = ref(false)

async function load() {
  try {
    const [c, l, j] = await Promise.all([adminSeoApi.config(), adminSeoApi.pushLogs(1), adminSeoApi.jobs()])
    config.value = c
    logs.value = l.items
    jobs.value = j.items
  } catch (e: any) {
    message.error(e?.message || 'SEO 状态加载失败')
  }
}
onMounted(load)

async function pushPending() {
  busy.value = 'push'
  try {
    const r = await adminSeoApi.push({ pending: true, force: forcePush.value })
    const parts = [`成功 ${r.success}`, `失败 ${r.fail}`]
    if (r.already) parts.push(`已推跳过 ${r.already}`)
    if (r.skipped) parts.push(`入待推 ${r.skipped}`)
    message.success(`推送完成：${parts.join(' / ')}`)
    load()
  } catch (e: any) {
    message.error(e?.message || '推送失败')
  } finally { busy.value = '' }
}

async function rebuild() {
  busy.value = 'rebuild'
  try {
    await adminSeoApi.rebuild()
    message.info('重建任务已排队（10s 合并窗口），稍后刷新查看状态')
    setTimeout(load, 12000)
  } catch (e: any) {
    message.error(e?.message || '触发失败')
  } finally { busy.value = '' }
}

const logColumns = [
  { title: '时间', key: 'created_at', width: 150, render: (r: any) => formatDateTime(r.created_at) },
  { title: '来源', key: 'triggered_by', width: 80 },
  {
    title: 'URL 数', key: 'urls', width: 80,
    render: (r: any) => (Array.isArray(r.urls) ? r.urls.length : 0),
  },
  {
    title: '结果', key: 'result', minWidth: 240, ellipsis: { tooltip: true },
    render: (r: any) => JSON.stringify(r.result),
  },
]

const jobStatusColor: Record<string, 'default' | 'success' | 'error' | 'warning' | 'info'> = {
  success: 'success', failed: 'error', running: 'info', skipped: 'warning',
}
const jobColumns = [
  { title: '#', key: 'id', width: 50 },
  { title: '时间', key: 'created_at', width: 150, render: (r: any) => formatDateTime(r.created_at) },
  {
    title: '状态', key: 'status', width: 90,
    render: (r: any) => h(NTag, { size: 'small', type: jobStatusColor[r.status] ?? 'default' }, () => r.status),
  },
  { title: '日志尾', key: 'log', ellipsis: { tooltip: true }, render: (r: any) => String(r.log ?? '').slice(-90) },
]
</script>

<template>
  <div>
    <h1 class="mb-5 text-2xl font-bold">SEO 面板</h1>

    <div class="mb-5 grid gap-4 md:grid-cols-3">
      <div class=" border border-line bg-surface p-5">
        <p class="text-xs text-ink-3">百度主动推送</p>
        <p class="mt-2 text-lg font-semibold">
          {{ config?.api_configured ? (config.push_enabled ? '已启用' : '已配置未启用') : '未配置 Token' }}
        </p>
        <p class="mt-1 text-xs text-ink-3">{{ config?.api_configured ? '发布后自动推送，同一地址只推一次' : '发布 URL 将进入待推队列，配置后一键补推' }}</p>
      </div>
      <div class=" border border-line bg-surface p-5">
        <p class="text-xs text-ink-3">前端重建</p>
        <p class="mt-2 text-lg font-semibold">
          {{ config?.rebuild_configured ? '已配置（裸机直连）'
              : config?.rebuild_watcher ? 'Watcher 模式（自动）'
              : '未配置（跳过重建）' }}
        </p>
        <p class="mt-1 text-xs text-ink-3">
          {{ config?.rebuild_configured ? config?.site_url
              : config?.rebuild_watcher ? '发布写重建请求，宿主机 cron 拉起构建（≤5 分钟）'
              : '配 REBUILD_SCRIPT（裸机）或 REBUILD_REQUEST_FILE（Docker）后发布即自动重建' }}
        </p>
      </div>
      <div class="flex items-center gap-2  border border-line bg-surface p-5">
        <n-checkbox v-model:checked="forcePush" size="small">忽略去重</n-checkbox>
        <n-button type="primary" size="small" :loading="busy === 'push'" @click="pushPending">批量补推待推 URL</n-button>
        <n-button size="small" :loading="busy === 'rebuild'" @click="rebuild">手动重建</n-button>
        <n-button tertiary size="small" @click="load">刷新</n-button>
      </div>
    </div>

    <h2 class="mb-2 text-sm font-semibold text-ink-2">重建任务</h2>
    <n-data-table size="small" :columns="jobColumns" :data="jobs" :max-height="260" :scroll-x="520" class="mb-8" />

    <h2 class="mb-2 text-sm font-semibold text-ink-2">推送日志</h2>
    <n-data-table size="small" :columns="logColumns" :data="logs" :max-height="360" :scroll-x="620" />
    <p v-if="!logs.length" class="py-6 text-center text-sm text-ink-3">暂无推送记录</p>
  </div>
</template>
