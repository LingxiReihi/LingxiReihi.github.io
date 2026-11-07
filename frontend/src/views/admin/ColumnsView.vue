<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import {
  NButton, NDataTable, NInput, NModal, NPopconfirm, NInputNumber, NSelect, useMessage,
} from 'naive-ui'
import { computed, h, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { adminColumnsApi } from '@/api'
import type { ColumnOut, ContentType } from '@/api/types'

const message = useMessage()
const router = useRouter()

const type = ref<ContentType>('article')
const TYPE_TABS: { key: ContentType; label: string }[] = [
  { key: 'article', label: '博客' },
  { key: 'model', label: '模型' },
  { key: 'chat', label: '杂谈' },
]

const items = ref<ColumnOut[]>([])
const loading = ref(false)
const newName = ref('')
const creating = ref(false)

/** 编辑弹窗：名称/slug/简介/排序 */
const editTarget = ref<ColumnOut | null>(null)
const editValue = ref({ name: '', slug: '', summary: '', sort_order: 0, parent_id: null as number | null })
const saving = ref(false)

async function load() {
  loading.value = true
  try {
    const d = await adminColumnsApi.list(type.value)
    items.value = d.items
  } catch (e: any) {
    message.error(e?.message || '栏目加载失败')
  } finally {
    loading.value = false
  }
}
watch(type, () => { newName.value = ''; load() })
onMounted(load)

async function create() {
  const name = newName.value.trim()
  if (!name) { message.warning('请输入栏目名称'); return }
  creating.value = true
  try {
    await adminColumnsApi.create({ name, type: type.value })
    message.success(`已创建栏目「${name}」`)
    newName.value = ''
    load()
  } catch (e: any) {
    message.error(e?.message || '创建失败')
  } finally {
    creating.value = false
  }
}

function openEdit(col: ColumnOut) {
  editTarget.value = col
  editValue.value = { name: col.name, slug: col.slug, summary: col.summary, sort_order: col.sort_order ?? 0, parent_id: col.parent_id ?? null }
}

async function confirmEdit() {
  const target = editTarget.value
  if (!target) return
  if (!editValue.value.name.trim()) { message.warning('名称不能为空'); return }
  saving.value = true
  try {
    await adminColumnsApi.update(target.id, {
      name: editValue.value.name.trim(),
      slug: editValue.value.slug.trim() || undefined,
      summary: editValue.value.summary,
      sort_order: editValue.value.sort_order ?? 0,
      parent_id: editValue.value.parent_id,
    })
    message.success('已保存')
    editTarget.value = null
    load()
  } catch (e: any) {
    message.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(col: ColumnOut) {
  try {
    const d = await adminColumnsApi.remove(col.id)
    message.success(`已删除，${d.detached} 篇文章解除归属`)
    load()
  } catch (e: any) {
    message.error(e?.message || '删除失败')
  }
}

// ── 层级（最多三级）：深度计算 / 后代排除 / DFS 树序 / 上级候选 ──
const byId = computed(() => new Map(items.value.map((c) => [c.id, c])))
function depthOf(c: ColumnOut) {
  let d = 0, p = c.parent_id
  while (p) { d++; p = byId.value.get(p)?.parent_id ?? null }
  return d
}
function isDescendant(c: ColumnOut, ancestorId: number) {
  let p: number | null | undefined = c.parent_id
  while (p) { if (p === ancestorId) return true; p = byId.value.get(p)?.parent_id ?? null }
  return false
}
const treeItems = computed(() => {
  const kids = new Map<number | null, ColumnOut[]>()
  for (const c of items.value) {
    const k = c.parent_id ?? null
    if (!kids.has(k)) kids.set(k, [])
    kids.get(k)!.push(c)
  }
  const out: ColumnOut[] = []
  const walk = (list: ColumnOut[]) => { for (const c of list) { out.push(c); walk(kids.get(c.id) ?? []) } }
  walk(kids.get(null) ?? [])
  return out
})
const parentOptions = computed(() => {
  const t = editTarget.value
  if (!t) return []
  return items.value
    .filter((c) => c.id !== t.id && !isDescendant(c, t.id) && depthOf(c) < 2)
    .map((c) => ({ label: `${'　'.repeat(depthOf(c))}${c.name}`, value: c.id }))
})

const columns: DataTableColumns<ColumnOut> = [
  {
    title: '名称', key: 'name', minWidth: 160,
    render: (row) => h('button', {
      class: 'flex items-center gap-1 text-left font-medium text-brand transition-colors hover:underline',
      style: { paddingLeft: `${depthOf(row) * 18}px` },
      title: `查看「${row.name}」栏目下的文章（含子栏目）`,
      onClick: () => router.push(`/admin/content?type=${type.value}&column=${encodeURIComponent(row.slug)}`),
    }, [depthOf(row) ? '└ ' : '', row.name]),
  },
  {
    title: 'Slug', key: 'slug', minWidth: 140, ellipsis: { tooltip: true },
    render: (row) => h('span', { class: 'text-xs text-ink-3' }, row.slug),
  },
  {
    title: '简介', key: 'summary', minWidth: 200, ellipsis: { tooltip: true },
    render: (row) => h('span', { class: 'text-xs text-ink-3' }, row.summary || '—'),
  },
  { title: '排序', key: 'sort_order', width: 70, render: (row) => String(row.sort_order ?? 0) },
  { title: '文章数', key: 'count', width: 80, render: (row) => h('span', { class: 'text-sm tabular-nums' }, String(row.count ?? 0)) },
  {
    title: '操作', key: 'actions', width: 120,
    render: (row) => h('div', { class: 'flex items-center gap-1' }, [
      h(NButton, { size: 'tiny', quaternary: true, onClick: () => openEdit(row) }, () => '编辑'),
      h(NPopconfirm, { onPositiveClick: () => remove(row) }, {
        trigger: () => h(NButton, { size: 'tiny', quaternary: true, type: 'error' }, () => '删除'),
        default: () => `删除后 ${row.count ?? 0} 篇文章将解除栏目归属，确定删除？`,
      }),
    ]),
  },
]
</script>

<template>
  <div>
    <div class="mb-4 flex flex-wrap items-center gap-3">
      <h1 class="text-2xl font-bold">栏目管理</h1>
      <!-- 类型切换：栏目按内容类型隔离（与标签同款规则） -->
      <div class="flex gap-1  border border-line bg-surface p-1">
        <button
          v-for="t in TYPE_TABS" :key="t.key"
          class=" px-4 py-1.5 text-sm transition-colors"
          :class="type === t.key ? 'bg-brand font-medium text-black' : 'text-ink-2 hover:bg-elevated hover:text-ink'"
          @click="type = t.key"
        >{{ t.label }}</button>
      </div>
      <div class="ml-auto flex items-center gap-2">
        <n-input
          v-model:value="newName" size="small" class="!w-44"
          :placeholder="`「${TYPE_TABS.find(t => t.key === type)?.label}」新栏目名称`" clearable @keyup.enter="create"
        />
        <n-button size="small" type="primary" :loading="creating" @click="create">＋ 新建栏目</n-button>
      </div>
    </div>

    <div class=" border border-line bg-surface p-4">
      <n-data-table
        :columns="columns" :data="treeItems" :loading="loading" size="small"
        :row-key="(r: ColumnOut) => r.id" :scroll-x="640"
      />
      <p v-if="!loading && !items.length" class="py-10 text-center text-sm text-ink-3">
        还没有栏目，在右上角创建第一个吧
      </p>
      <p v-else-if="items.length" class="mt-3 text-xs text-ink-3">共 {{ items.length }} 个栏目 · 点击名称可查看栏目内文章（含子栏目） · 编辑中可设上级栏目，最多三级</p>
    </div>

    <!-- 编辑弹窗 -->
    <n-modal
      :show="!!editTarget" preset="card" title="编辑栏目"
      style="width: 420px; max-width: 94vw; border-radius: 16px"
      @update:show="(v: boolean) => { if (!v) editTarget = null }"
    >
      <div class="space-y-3">
        <div>
          <p class="mb-1 text-xs text-ink-3">名称</p>
          <n-input v-model:value="editValue.name" placeholder="栏目名称" :disabled="saving" />
        </div>
        <div>
          <p class="mb-1 text-xs text-ink-3">Slug（改后线上旧链接会 404，谨慎修改）</p>
          <n-input v-model:value="editValue.slug" placeholder="留空则不修改" :disabled="saving" />
        </div>
        <div>
          <p class="mb-1 text-xs text-ink-3">简介</p>
          <n-input v-model:value="editValue.summary" type="textarea" :rows="2" placeholder="栏目简介（展示在栏目页）" :disabled="saving" />
        </div>
        <div>
          <p class="mb-1 text-xs text-ink-3">上级栏目（留空为顶级，最多三级）</p>
          <n-select v-model:value="editValue.parent_id" :options="parentOptions" placeholder="顶级栏目" clearable :disabled="saving" />
        </div>
        <div>
          <p class="mb-1 text-xs text-ink-3">排序</p>
          <n-input-number v-model:value="editValue.sort_order" size="small" class="!w-32" :disabled="saving" />
        </div>
      </div>
      <div class="mt-4 flex justify-end gap-2">
        <n-button size="small" @click="editTarget = null">取消</n-button>
        <n-button size="small" type="primary" :loading="saving" @click="confirmEdit">保存</n-button>
      </div>
    </n-modal>
  </div>
</template>
