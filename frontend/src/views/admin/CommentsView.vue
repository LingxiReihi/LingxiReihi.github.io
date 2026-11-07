<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import {
  NButton, NDataTable, NImage, NModal, NPopconfirm, NSpace, NTag,
  useDialog, useMessage,
} from 'naive-ui'
import { h, onMounted, ref } from 'vue'

import { adminCommentsApi } from '@/api'
import type { AdminComment } from '@/api/types'
import { formatDateTime } from '@/utils/format'

const message = useMessage()
const dialog = useDialog()

const items = ref<AdminComment[]>([])
const checked = ref<number[]>([])
const total = ref(0)
const pending = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const status = ref<string>('pending')
const detail = ref<AdminComment | null>(null)

function openDetail(row: AdminComment) { detail.value = row }
async function actFromCard(st: 'approved' | 'rejected') {
  const id = detail.value?.id
  detail.value = null
  if (id) await moderate([id], st)
}

const PILLS = [
  { value: 'pending', label: '待审核' },
  { value: 'approved', label: '已通过' },
  { value: 'rejected', label: '已拒绝' },
  { value: '', label: '全部' },
]
const STATUS_META: Record<string, { label: string; type: 'warning' | 'success' | 'error' | 'default' }> = {
  pending: { label: '待审核', type: 'warning' },
  approved: { label: '已通过', type: 'success' },
  rejected: { label: '已拒绝', type: 'error' },
}

async function load() {
  loading.value = true
  try {
    const d = await adminCommentsApi.list({
      status: status.value || undefined, page: page.value, page_size: pageSize,
    })
    items.value = d.items
    total.value = d.total
    pending.value = d.pending
    checked.value = []
  } catch (e: any) {
    message.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(load)

function switchStatus(s: string) {
  status.value = s
  page.value = 1
  load()
}

async function moderate(ids: number[], st: string) {
  if (!ids.length) { message.warning('请先勾选评论'); return }
  try {
    await adminCommentsApi.moderate(ids, st)
    message.success(st === 'approved' ? '已通过' : st === 'rejected' ? '已拒绝' : '已转待审核')
    load()
  } catch (e: any) {
    message.error(e?.message || '操作失败')
  }
}

function remove(id: number) {
  dialog.warning({
    title: '删除评论', content: '删除后不可恢复，确定？',
    positiveText: '删除', negativeText: '取消',
    onPositiveClick: async () => {
      await adminCommentsApi.remove(id)
      message.success('已删除')
      load()
    },
  })
}

const columns: DataTableColumns<AdminComment> = [
  { type: 'selection' },
  {
    title: '用户', key: 'nickname', width: 180,
    render: (row) => h('div', { class: 'flex items-center gap-2' }, [
      h(NImage, { src: row.avatar, width: 28, height: 28, class: '!rounded-full', objectFit: 'cover', previewDisabled: true }),
      h('div', {}, [
        h('div', { class: 'text-sm' }, row.nickname),
        h('div', { class: 'text-xs text-ink-3' }, row.email),
      ]),
    ]),
  },
  {
    title: '评论内容', key: 'body', minWidth: 220,
    render: (row) => h('div', { class: 'cursor-pointer group/body', title: '点击查看完整内容', onClick: () => openDetail(row) }, [
      h('div', { class: 'line-clamp-2 text-sm group-hover/body:text-brand' }, row.body),
      h('div', { class: 'text-xs text-ink-3' }, `《${row.content_title ?? '已删除内容'}》`),
    ]),
  },
  {
    title: '状态', key: 'status', width: 80,
    render: (row) => {
      const m = STATUS_META[row.status] ?? { label: row.status, type: 'default' as const }
      return h(NTag, { size: 'small', type: m.type, bordered: false }, () => m.label)
    },
  },
  {
    title: '提交', key: 'created_at', width: 150,
    render: (row) => h('div', {}, [
      h('div', { class: 'text-xs' }, formatDateTime(row.created_at)),
      h('div', { class: 'text-xs text-ink-3' }, row.submit_ip),
    ]),
  },
  {
    title: '操作', key: 'ops', width: 170,
    render: (row) => h(NSpace, { size: 4 }, () => [
      row.status !== 'approved' && h(NButton, { size: 'tiny', type: 'primary', onClick: () => moderate([row.id], 'approved') }, () => '通过'),
      row.status !== 'rejected' && h(NButton, { size: 'tiny', onClick: () => moderate([row.id], 'rejected') }, () => '拒绝'),
      h(NPopconfirm, { onPositiveClick: () => remove(row.id) }, {
        trigger: () => h(NButton, { size: 'tiny', quaternary: true, type: 'error' }, () => '删除'),
        default: () => '删除该评论？',
      }),
    ].filter(Boolean) as any),
  },
]
</script>

<template>
  <div>
    <div class="mb-4 flex flex-wrap items-center gap-3">
      <h1 class="text-2xl font-bold">评论管理</h1>
      <span class="text-sm text-ink-3">{{ total }} 条<template v-if="pending"> · 待审 {{ pending }}</template></span>
      <div class="ml-auto flex items-center gap-2">
        <button
          v-for="p in PILLS" :key="p.value"
          class="rounded-full border px-3 py-1 text-xs transition-colors"
          :class="status === p.value ? 'border-brand bg-brand/10 text-brand' : 'border-line text-ink-3 hover:border-brand/50'"
          @click="switchStatus(p.value)"
        >
          {{ p.label }}<template v-if="p.value === 'pending' && pending"> ({{ pending }})</template>
        </button>
      </div>
    </div>

    <div v-if="checked.length" class="mb-3 flex items-center gap-2 text-sm">
      <span class="text-ink-3">已选 {{ checked.length }} 条</span>
      <n-button size="small" type="primary" @click="moderate(checked, 'approved')">批量通过</n-button>
      <n-button size="small" @click="moderate(checked, 'rejected')">批量拒绝</n-button>
    </div>

    <n-data-table
      :columns="columns" :data="items" :loading="loading" :row-key="(r: AdminComment) => r.id"
      v-model:checked-row-keys="checked" size="small" :pagination="false" :scroll-x="900"
    />
    <div v-if="total > pageSize" class="mt-4 flex justify-end">
      <button class="text-sm text-ink-3 disabled:opacity-40" :disabled="page <= 1" @click="page--; load()">上一页</button>
      <span class="mx-3 py-1 text-sm text-ink-3">{{ page }} / {{ Math.ceil(total / pageSize) }}</span>
      <button class="text-sm text-ink-3 disabled:opacity-40" :disabled="page >= Math.ceil(total / pageSize)" @click="page++; load()">下一页</button>
    </div>

    <n-modal
      :show="!!detail" preset="card" title="评论内容" style="width: 520px; max-width: 94vw"
      @update:show="detail = null"
    >
      <div v-if="detail">
        <div class="flex items-center gap-3">
          <n-image :src="detail.avatar" width="40" height="40" class="!rounded-full" :preview-disabled="true" object-fit="cover" />
          <div class="min-w-0">
            <p class="text-sm font-medium">{{ detail.nickname }}</p>
            <p class="truncate text-xs text-ink-3">{{ detail.email }}</p>
          </div>
          <n-tag
            class="ml-auto" size="small" :bordered="false"
            :type="STATUS_META[detail.status]?.type ?? 'default'"
          >{{ STATUS_META[detail.status]?.label ?? detail.status }}</n-tag>
        </div>
        <p class="mt-4 whitespace-pre-wrap break-words  border border-line bg-elevated p-4 text-sm leading-relaxed">{{ detail.body }}</p>
        <p class="mt-3 text-xs text-ink-3">
          关联：《{{ detail.content_title ?? '已删除内容' }}》 · {{ formatDateTime(detail.created_at) }} · IP {{ detail.submit_ip }}
        </p>
        <div class="mt-5 flex justify-end gap-2">
          <n-button size="small" @click="detail = null">关闭</n-button>
          <n-button size="small" :disabled="detail.status === 'rejected'" @click="actFromCard('rejected')">拒绝</n-button>
          <n-button size="small" type="primary" :disabled="detail.status === 'approved'" @click="actFromCard('approved')">通过</n-button>
        </div>
      </div>
    </n-modal>
  </div>
</template>
