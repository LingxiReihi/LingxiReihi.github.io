<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import {
  NButton, NDataTable, NInput, NModal, NPopconfirm, useMessage,
} from 'naive-ui'
import { computed, h, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { adminTagsApi } from '@/api'
import type { ContentType, TagOut } from '@/api/types'

const message = useMessage()
const router = useRouter()

const type = ref<ContentType>('article')
const TYPE_TABS: { key: ContentType; label: string }[] = [
  { key: 'article', label: '博客' },
  { key: 'model', label: '模型' },
  { key: 'chat', label: '杂谈' },
]
const currentLabel = computed(() => TYPE_TABS.find((t) => t.key === type.value)?.label ?? '')

const items = ref<TagOut[]>([])
const loading = ref(false)
const newName = ref('')
const creating = ref(false)

/** 重命名弹窗：type 不可改，仅改名称 */
const renameTarget = ref<TagOut | null>(null)
const renameValue = ref('')
const renaming = ref(false)

async function load() {
  loading.value = true
  try {
    const d = await adminTagsApi.list(type.value)
    items.value = d.items
  } catch (e: any) {
    message.error(e?.message || '标签加载失败')
  } finally {
    loading.value = false
  }
}
watch(type, () => { newName.value = ''; load() })
onMounted(load)

async function create() {
  const name = newName.value.trim()
  if (!name) { message.warning('请输入标签名称'); return }
  creating.value = true
  try {
    await adminTagsApi.create(name, type.value)
    message.success(`已在「${currentLabel.value}」下创建「${name}」`)
    newName.value = ''
    load()
  } catch (e: any) {
    message.error(e?.message || '创建失败')
  } finally {
    creating.value = false
  }
}

function openRename(tag: TagOut) {
  renameTarget.value = tag
  renameValue.value = tag.name
}

async function confirmRename() {
  const target = renameTarget.value
  const name = renameValue.value.trim()
  if (!target || !name) return
  renaming.value = true
  try {
    await adminTagsApi.rename(target.id, name)
    message.success('已重命名')
    renameTarget.value = null
    load()
  } catch (e: any) {
    message.error(e?.message || '重命名失败')
  } finally {
    renaming.value = false
  }
}

async function remove(tag: TagOut) {
  try {
    await adminTagsApi.remove(tag.id)
    message.success(`已删除，从 ${tag.count ?? 0} 篇内容上解除关联`)
    load()
  } catch (e: any) {
    message.error(e?.message || '删除失败')
  }
}

const columns: DataTableColumns<TagOut> = [
  {
    title: '名称', key: 'name', minWidth: 140,
    render: (row) => h('button', {
      class: 'text-left font-medium text-brand transition-colors hover:underline',
      title: `查看使用「${row.name}」的内容`,
      onClick: () => router.push(`/admin/content?type=${type.value}&tag=${encodeURIComponent(row.slug)}`),
    }, row.name),
  },
  {
    title: 'Slug', key: 'slug', minWidth: 160, ellipsis: { tooltip: true },
    render: (row) => h('span', { class: 'text-xs text-ink-3' }, row.slug),
  },
  {
    title: '使用次数', key: 'count', width: 90,
    render: (row) => h('span', { class: 'text-sm tabular-nums' }, String(row.count ?? 0)),
  },
  {
    title: '操作', key: 'actions', width: 140,
    render: (row) => h('div', { class: 'flex items-center gap-1' }, [
      h(NButton, { size: 'tiny', quaternary: true, onClick: () => openRename(row) }, () => '重命名'),
      h(NPopconfirm, { onPositiveClick: () => remove(row) }, {
        trigger: () => h(NButton, { size: 'tiny', quaternary: true, type: 'error' }, () => '删除'),
        default: () => `将从 ${row.count ?? 0} 篇内容上移除该标签，确定删除？`,
      }),
    ]),
  },
]
</script>

<template>
  <div>
    <div class="mb-4 flex flex-wrap items-center gap-3">
      <h1 class="text-2xl font-bold">标签管理</h1>
      <!-- 类型切换：标签体系按内容类型隔离（不依赖 Naive Tabs 样式） -->
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
          :placeholder="`「${currentLabel}」新标签名称`" clearable @keyup.enter="create"
        />
        <n-button size="small" type="primary" :loading="creating" @click="create">＋ 新建标签</n-button>
      </div>
    </div>

    <div class=" border border-line bg-surface p-4">
      <n-data-table
        :columns="columns" :data="items" :loading="loading" size="small"
        :row-key="(r: TagOut) => r.id" :scroll-x="560"
      />
      <p v-if="!loading && !items.length" class="py-10 text-center text-sm text-ink-3">
        「{{ currentLabel }}」下还没有标签，在右上角创建第一个吧
      </p>
      <p v-else-if="items.length" class="mt-3 text-xs text-ink-3">共 {{ items.length }} 个标签 · 点击名称可查看使用该标签的内容 · 不同类型下的标签相互隔离，同名标签可在各类型下独立存在</p>
    </div>

    <!-- 重命名弹窗 -->
    <n-modal
      :show="!!renameTarget" preset="card" title="重命名标签"
      style="width: 380px; max-width: 94vw; border-radius: 16px"
      @update:show="(v: boolean) => { if (!v) renameTarget = null }"
    >
      <p class="mb-2 text-xs text-ink-3">重命名将同步到「{{ currentLabel }}」下使用该标签的全部{{ renameTarget?.count ?? 0 }}篇内容。</p>
      <n-input v-model:value="renameValue" placeholder="标签名称" :disabled="renaming" @keyup.enter="confirmRename" />
      <div class="mt-4 flex justify-end gap-2">
        <n-button size="small" @click="renameTarget = null">取消</n-button>
        <n-button size="small" type="primary" :loading="renaming" @click="confirmRename">确定</n-button>
      </div>
    </n-modal>
  </div>
</template>
