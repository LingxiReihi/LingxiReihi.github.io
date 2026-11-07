<script setup lang="ts">
import {
  NButton, NInput, NSelect, useMessage,
} from 'naive-ui'
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import { adminLogsApi } from '@/api'
import type { LogFile } from '@/api'
import { useDebounceFn } from '@vueuse/core'

const message = useMessage()

const files = ref<LogFile[]>([])
const file = ref('app.log')
const lines = ref(300)
const grep = ref('')
const logLines = ref<string[]>([])
const total = ref(0)
const loading = ref(false)
const preRef = ref<HTMLElement | null>(null)

const fileOptions = computed(() => files.value.map((f) => ({
  label: `${f.name}（${(f.size / 1024).toFixed(1)} KB · ${f.mtime}）`,
  value: f.name,
})))
const linesOptions = [100, 300, 1000, 5000].map((n) => ({ label: `后 ${n} 行`, value: n }))

async function loadFiles() {
  try {
    const d = await adminLogsApi.files()
    files.value = d.items
    if (!d.items.some((f) => f.name === file.value) && d.items.length) file.value = d.items[0].name
  } catch (e: any) {
    message.error(e?.message || '日志列表加载失败')
  }
}

async function loadTail() {
  loading.value = true
  try {
    const d = await adminLogsApi.tail(file.value, lines.value, grep.value || undefined)
    logLines.value = d.lines
    total.value = d.total
    nextTick(() => { if (preRef.value) preRef.value.scrollTop = preRef.value.scrollHeight })
  } catch (e: any) {
    message.error(e?.message || '日志读取失败')
  } finally {
    loading.value = false
  }
}

const debouncedTail = useDebounceFn(loadTail, 350)
watch([file, lines], loadTail)
watch(grep, debouncedTail)

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

async function downloadCurrent() {
  try {
    saveBlob(await adminLogsApi.download(file.value), file.value)
  } catch (e: any) { message.error(e?.message || '下载失败') }
}
async function downloadArchive() {
  try {
    saveBlob(await adminLogsApi.archive(), `logs-${Date.now()}.zip`)
  } catch (e: any) { message.error(e?.message || '打包失败') }
}

onMounted(async () => { await loadFiles(); loadTail() })
</script>

<template>
  <div>
    <div class="mb-4 flex flex-wrap items-center gap-3">
      <h1 class="text-2xl font-bold">日志</h1>
      <p class="text-xs text-ink-3">app.log 业务事件（上传/发布/推送/登录/审核/重建）· access.log 每请求一行 · 单文件 5MB 轮转保留 5 份</p>
      <div class="ml-auto flex flex-wrap items-center gap-2">
        <n-select v-model:value="file" size="small" class="!w-64" :options="fileOptions" />
        <n-select v-model:value="lines" size="small" class="!w-28" :options="linesOptions" />
        <n-input v-model:value="grep" size="small" class="!w-40" placeholder="过滤关键词" clearable />
        <n-button size="small" :loading="loading" @click="loadFiles().then(loadTail)">刷新</n-button>
        <n-button size="small" @click="downloadCurrent">下载此文件</n-button>
        <n-button size="small" type="primary" @click="downloadArchive">打包下载全部</n-button>
      </div>
    </div>

    <div class=" border border-line bg-surface">
      <div class="flex items-center justify-between border-b border-line px-4 py-2 text-xs text-ink-3">
        <span>{{ file }} · 匹配 {{ total }} 行（显示后 {{ logLines.length }} 行）</span>
        <span>UTC 时间</span>
      </div>
      <pre
        ref="preRef"
        class="max-h-[calc(100vh-280px)] min-h-[300px] overflow-auto whitespace-pre-wrap break-all p-4 font-mono text-xs leading-5 text-ink-2"
      >{{ logLines.join('\n') || (loading ? '加载中…' : '（无匹配日志）') }}</pre>
    </div>
  </div>
</template>
