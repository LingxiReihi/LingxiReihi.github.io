<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import {
  NButton, NDataTable, NDropdown, NInput, NPagination, NSelect,
  useDialog, useMessage,
} from 'naive-ui'
import { h, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { adminColumnsApi, adminContentsApi, adminTagsApi } from '@/api'
import type { AdminContent } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'

const auth = useAuthStore()

const router = useRouter()
const route = useRoute()
const message = useMessage()
const dialog = useDialog()

const type = ref<'article' | 'model' | 'chat'>('article')
const TYPE_TABS = [
  { key: 'article', label: '文章' },
  { key: 'model', label: '模型' },
  { key: 'chat', label: '杂谈' },
] as const
const NEW_MENU = [
  { key: 'article', label: '＋ 新建文章' },
  { key: 'model', label: '＋ 新建模型' },
  { key: 'chat', label: '＋ 新建杂谈' },
]
const STATUS_OPTIONS = [
  { label: '草稿', value: 'draft' },
  { label: '已发布', value: 'published' },
  { label: '已下架', value: 'archived' },
]
const items = ref<AdminContent[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const q = ref('')
const statusFilter = ref<string | null>(null)
const tagFilter = ref<string | null>(null)
const tagOptions = ref<{ label: string; value: string }[]>([])
const columnFilter = ref<string | null>(null)
const columnOptions = ref<{ label: string; value: string }[]>([])
// 批量挂栏目用 id 值（筛选下拉是 slug 值）
const bulkColOptions = ref<{ label: string; value: number }[]>([])
const mineOnly = ref(false)

const STATUS_META: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'var(--c-text-3)' },
  published: { label: '已发布', color: 'var(--c-success)' },
  archived: { label: '已下架', color: 'var(--c-warning)' },
}

async function load() {
  loading.value = true
  try {
    const d = await adminContentsApi.list({
      type: type.value,
      q: q.value || undefined,
      status: statusFilter.value || undefined,
      tag: tagFilter.value || undefined,
      column: columnFilter.value || undefined,
      mine: mineOnly.value ? 1 : undefined,
      page: page.value,
      page_size: pageSize,
    })
    items.value = d.items
    total.value = d.total
  } catch (e: any) {
    message.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function refilter() {
  page.value = 1
  load()
}

function resetFilters() {
  q.value = ''
  statusFilter.value = null
  tagFilter.value = null
  columnFilter.value = null
  mineOnly.value = false
  refilter()
}

async function loadColumns(forType = type.value) {
  try {
    const d = await adminColumnsApi.list(forType)
    // 异步返回时类型可能已切换，丢弃过期结果
    if (forType !== type.value) return
    const byId = new Map(d.items.map((c) => [c.id, c]))
    const depthOf = (c: { parent_id?: number | null }) => {
      let dep = 0, p = c.parent_id
      while (p) { dep++; p = byId.get(p)?.parent_id ?? null }
      return dep
    }
    columnOptions.value = d.items.map((c) => ({ label: `${'　'.repeat(depthOf(c))}${c.name}`, value: c.slug }))
    bulkColOptions.value = d.items.map((c) => ({ label: `${'　'.repeat(depthOf(c))}${c.name}`, value: c.id }))
  } catch { /* 非关键 */ }
}

async function loadTags(forType = type.value) {
  try {
    const d = await adminTagsApi.list(forType)
    // 异步返回时类型可能已切换，丢弃过期结果
    if (forType !== type.value) return
    tagOptions.value = d.items.map((t) => ({ label: t.name, value: t.slug }))
  } catch { /* 忽略 */ }
}

onMounted(() => {
  // 支持 /admin/content?type=article&tag=slug&column=slug 直达（标签/栏目页点击跳入）
  const qt = String(route.query.type ?? '')
  if (qt === 'model' || qt === 'chat') type.value = qt
  if (route.query.tag) tagFilter.value = String(route.query.tag)
  if (route.query.column) columnFilter.value = String(route.query.column)
  load()
  loadTags()
  loadColumns()
})

function setType(t: 'article' | 'model' | 'chat') {
  type.value = t
  tagFilter.value = null // 标签按类型隔离，切类型时清掉旧筛选
  columnFilter.value = null
  checkedKeys.value = []
  page.value = 1
  load()
  loadTags(t)
  loadColumns(t)
}

function createNew(t: string) {
  router.push(`/admin/content/new?type=${t}`)
}

async function act(row: AdminContent, key: string) {
  try {
    if (key === 'edit') router.push(`/admin/content/${row.id}/edit`)
    else if (key === 'dashboard') router.push(`/admin/content/${row.id}/dashboard`)
    else if (key === 'preview') {
      const path = row.type === 'article' ? `/blog/${row.slug}`
        : row.type === 'model' ? `/models/${row.slug}`
        : `/chats/${row.id}`
      window.open(path, '_blank')
    }
    else if (key === 'publish' || key === 'unpublish') {
      const d = await adminContentsApi.setStatus(row.id, key === 'publish' ? 'published' : 'archived')
      message.success(key === 'publish' ? '已发布 ✓ 查看前台' : '已下架', { duration: 5000 })
      if (key === 'publish' && d?.pipeline?.queued) message.info('重建/推送流水线已排队（≤10s 合并窗口）', { duration: 5000 })
      load()
    } else if (key === 'resetLikes') {
      dialog.warning({
        title: '重置点赞',
        content: `「${row.title}」的 ${row.likes} 个赞将清零，不可恢复。确定？`,
        positiveText: '重置',
        negativeText: '取消',
        onPositiveClick: async () => {
          await adminContentsApi.resetLikes(row.id)
          message.success('点赞数已重置')
          load()
        },
      })
    } else if (key === 'delete') {
      dialog.warning({
        title: '删除内容',
        content: `「${row.title}」将被永久删除，不可恢复。确定？`,
        positiveText: '删除',
        negativeText: '取消',
        onPositiveClick: async () => {
          await adminContentsApi.remove(row.id)
          message.success('已删除')
          load()
        },
      })
    }
  } catch (e: any) {
    message.error(e?.message || '操作失败')
  }
}

// ── 批量挂栏目 ──
const checkedKeys = ref<number[]>([])
const bulkCol = ref<number | null>(null)
const bulkBusy = ref(false)
const selectionCol = { type: 'selection' as const }

async function applyBulk(columnId: number | null) {
  if (!checkedKeys.value.length) return
  const target = columnId === -1 ? null : (columnId ?? bulkCol.value)
  if (target === null && columnId === null) {
    message.warning('请先在下拉中选择要移入的栏目')
    return
  }
  bulkBusy.value = true
  try {
    const d = await adminContentsApi.columnBulk(checkedKeys.value, target)
    message.success(`已${target ? '加入栏目' : '移出栏目'} ${d.updated} 条${d.skipped ? `，${d.skipped} 条类型不符跳过` : ''}${d.denied?.length ? `，${d.denied.length} 条非你所有已跳过` : ''}`)
    checkedKeys.value = []
    bulkCol.value = null
    load()
    loadColumns()
  } catch (e: any) {
    message.error(e?.message || '操作失败')
  } finally {
    bulkBusy.value = false
  }
}

const columns: DataTableColumns<AdminContent> = [
  selectionCol as any,
  {
    title: '标题', key: 'title', width: 240, minWidth: 240, ellipsis: { tooltip: true },
    render: (row) => h('div', [
      h('a', {
        class: 'cursor-pointer font-medium hover:text-brand',
        href: `/admin/content/${row.id}/dashboard`,
        title: '点击进入内容仪表盘',
        onClick: (e: MouseEvent) => { e.preventDefault(); router.push(`/admin/content/${row.id}/dashboard`) },
      }, row.title),
      row.slug ? h('span', { class: 'ml-2 text-xs opacity-50' }, `/${row.slug}`) : null,
    ]),
  },
  {
    title: '状态', key: 'status', width: 90,
    render: (row) => {
      const m = STATUS_META[row.status] ?? STATUS_META.draft
      return h('span', { class: 'inline-flex items-center gap-1.5 text-xs' }, [
        h('i', { class: 'h-2 w-2 rounded-full', style: { background: m.color } }),
        m.label,
      ])
    },
  },
  {
    title: '栏目', key: 'column', width: 100,
    render: (row) => row.column
      ? h('span', { class: 'text-xs text-ink-2' }, row.column.name)
      : h('span', { class: 'text-xs text-ink-3' }, '—'),
  },
  {
    title: '标签', key: 'tags', width: 160,
    render: (row) => row.tags.map((t) => t.name).join('、') || '—',
  },
  {
    title: '点赞', key: 'likes', width: 60,
    render: (row) => h('span', { class: 'text-sm tabular-nums' }, String(row.likes ?? 0)),
  },
  {
    title: '评论', key: 'comment_count', width: 60,
    render: (row) => h('span', { class: 'text-sm tabular-nums' }, String(row.comment_count ?? 0)),
  },
  {
    title: '归属', key: 'owner_nickname', width: 90,
    render: (row) => h('span', {
      class: row.can_edit === false ? 'text-xs text-ink-3' : 'text-xs text-ink-2',
      title: row.denied_reason || undefined,
    }, row.owner_nickname || '未归属'),
  },
  { title: '更新时间', key: 'updated_at', width: 140, render: (row) => formatDateTime(row.updated_at) },
  {
    title: '操作', key: 'actions', width: 70,
    render: (row) =>
      h(NDropdown as any, {
        trigger: 'click',
        options: [
          { key: 'dashboard', label: '仪表盘' },
          { key: 'edit', label: '编辑', disabled: !row.can_edit },
          ...(row.status === 'published'
            ? [{ key: 'preview', label: '查看前台' }, { key: 'unpublish', label: '下架', disabled: !row.can_edit }]
            : [{ key: 'publish', label: '发布', disabled: !row.can_edit }]),
          { type: 'divider', key: 'd1' },
          { key: 'resetLikes', label: '重置点赞', disabled: !row.can_edit },
          { key: 'delete', label: '删除', disabled: !row.can_delete },
        ],
        onSelect: (k: string) => act(row, k),
      }, { default: () => h(NButton, { size: 'tiny', quaternary: true, title: row.denied_reason || undefined }, () => '···') }),
  },
]
</script>

<template>
  <div>
    <div class="mb-4 flex flex-wrap items-center gap-3">
      <h1 class="text-2xl font-bold">内容管理</h1>
      <!-- 类型切换：自绘按钮组（不依赖 Naive Tabs 样式） -->
      <div class="flex gap-1  border border-line bg-surface p-1">
        <button
          v-for="t in TYPE_TABS" :key="t.key"
          class=" px-4 py-1.5 text-sm transition-colors"
          :class="type === t.key ? 'bg-brand font-medium text-black' : 'text-ink-2 hover:bg-elevated hover:text-ink'"
          @click="setType(t.key)"
        >{{ t.label }}</button>
      </div>
      <n-dropdown v-if="auth.can('content:write')" trigger="click" :options="NEW_MENU" @select="createNew">
        <n-button class="ml-auto" type="primary">＋ 新建内容 ▾</n-button>
      </n-dropdown>
    </div>

    <div class="mb-3 flex flex-wrap items-center gap-2">
      <n-input v-model:value="q" size="small" placeholder="搜索标题/摘要" clearable class="!w-56" @keyup.enter="refilter()" @clear="refilter()" />
      <n-select
        v-model:value="statusFilter" size="small" class="!w-32" :options="STATUS_OPTIONS"
        placeholder="发布状态" clearable @update:value="refilter()"
      />
      <n-select
        v-model:value="tagFilter" size="small" class="!w-36" :options="tagOptions"
        placeholder="标签" filterable clearable @update:value="refilter()"
      />
      <n-select
        v-model:value="columnFilter" size="small" class="!w-36" :options="columnOptions"
        placeholder="栏目" filterable clearable @update:value="refilter()"
      />
      <button
        class=" border px-2.5 py-1 text-xs transition-colors"
        :class="mineOnly ? 'border-brand bg-brand/10 text-brand' : 'border-line bg-surface text-ink-2 hover:text-ink'"
        @click="mineOnly = !mineOnly; refilter()"
      >只看我的</button>
      <span class="text-xs text-ink-3">共 {{ total }} 条</span>
      <button
        v-if="q || statusFilter || tagFilter || columnFilter || mineOnly"
        class="text-xs text-brand hover:underline"
        @click="resetFilters"
      >清除筛选</button>
    </div>

    <div v-if="checkedKeys.length && auth.can('content:write')" class="mb-3 flex flex-wrap items-center gap-2  border border-brand/40 bg-brand/5 px-3 py-2 text-sm">
      <span class="text-brand">已选 {{ checkedKeys.length }} 条</span>
      <n-select
        v-model:value="bulkCol" size="small" class="!w-44" :options="bulkColOptions"
        placeholder="选择目标栏目" filterable clearable
      />
      <n-button size="small" type="primary" :loading="bulkBusy" @click="applyBulk(null)">加入栏目</n-button>
      <n-button size="small" :loading="bulkBusy" @click="applyBulk(-1)">移出栏目</n-button>
      <button class="ml-auto text-xs text-ink-3 hover:text-ink" @click="checkedKeys = []">取消选择</button>
    </div>

    <n-data-table
      :columns="columns" :data="items" :loading="loading" :row-key="(r: AdminContent) => r.id"
      size="small" :pagination="false" :scroll-x="800"
      :checked-row-keys="checkedKeys" @update:checked-row-keys="(v: any) => checkedKeys = v as number[]"
    />
    <div v-if="total > pageSize" class="mt-4 flex justify-end">
      <n-pagination v-model:page="page" :item-count="total" :page-size="pageSize" @update:page="load" />
    </div>
  </div>
</template>
