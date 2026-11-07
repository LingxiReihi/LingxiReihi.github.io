<script setup lang="ts">
import {
  NButton, NDatePicker, NInput, NModal, NPopconfirm, NTag, useMessage,
} from 'naive-ui'
import { computed, onMounted, ref } from 'vue'

import { adminAnnouncementsApi } from '@/api'
import type { Announcement } from '@/api/types'
import { renderMd } from '@/composables/useMd'

const message = useMessage()
const items = ref<Announcement[]>([])
const loading = ref(false)

/** 正文只走 Markdown 渲染（TOC 用不上，忽略第二返回值的 html） */
const bodies = computed(() => new Map(items.value.map((i) => [i.id, renderMd(i.body_md).html])))

async function load() {
  loading.value = true
  try {
    items.value = (await adminAnnouncementsApi.list()).items
  } catch (e: any) {
    message.error(e?.message || '公告加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(load)

const today = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const fmtDate = (iso: string | null) => (iso ? iso.slice(0, 10) : null)

// —— 新建/编辑弹窗（照 TagsView 样板：自控 show + preset card） ——
type EditTarget = { id: number | null; title: string; body_md: string; date: string | null }
const show = ref(false)
const edit = ref<EditTarget | null>(null)
const mode = ref<'edit' | 'preview'>('edit')
const saving = ref(false)
const previewHtml = computed(() => (edit.value ? renderMd(edit.value.body_md).html : ''))

function openCreate() {
  edit.value = { id: null, title: '', body_md: '', date: today() }
  mode.value = 'edit'
  show.value = true
}
function openEdit(it: Announcement) {
  edit.value = { id: it.id, title: it.title, body_md: it.body_md, date: fmtDate(it.published_at ?? it.created_at) }
  mode.value = 'edit'
  show.value = true
}

async function save() {
  const e = edit.value
  if (!e) return
  const title = e.title.trim()
  if (!title) { message.warning('请输入公告标题'); return }
  saving.value = true
  const body = { title, body_md: e.body_md, status: e.date ? ('published' as const) : ('draft' as const), published_at: e.date }
  try {
    if (e.id == null) await adminAnnouncementsApi.create(body)
    else await adminAnnouncementsApi.update(e.id, body)
    message.success('已保存')
    show.value = false
    await load()
  } catch (err: any) {
    message.error(err?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(it: Announcement) {
  try {
    await adminAnnouncementsApi.remove(it.id)
    message.success('已删除')
    await load()
  } catch (e: any) {
    message.error(e?.message || '删除失败')
  }
}
</script>

<template>
  <div>
    <div class="mb-5 flex items-center gap-3">
      <h1 class="text-2xl font-bold">更新公告</h1>
      <span class="text-xs text-ink-3">{{ items.length }} 条</span>
      <n-button class="ml-auto" size="tiny" type="primary" @click="openCreate">＋ 新建</n-button>
    </div>
    <div class=" border border-line bg-surface p-4">
      <div v-if="loading" class="py-6 text-center text-sm text-ink-3">加载中…</div>
      <p v-else-if="!items.length" class="py-6 text-center text-sm text-ink-3">
        还没有公告 —— 点「新建」记录每次上线变更
      </p>
      <ul v-else class="space-y-3">
        <li v-for="it in items" :key="it.id" class=" border border-line p-3">
          <div class="flex flex-wrap items-center gap-2">
            <n-tag size="small" :type="it.status === 'published' ? 'success' : 'default'">
              {{ it.status === 'published' ? '已发布' : '草稿' }}
            </n-tag>
            <span class="font-medium">{{ it.title }}</span>
            <span class="text-xs text-ink-3">{{ fmtDate(it.published_at ?? it.created_at) }}
              <template v-if="it.created_by"> · {{ it.created_by }}</template></span>
            <span class="ml-auto flex gap-1">
              <n-button size="tiny" tertiary @click="openEdit(it)">编辑</n-button>
              <n-popconfirm @positive-click="remove(it)">
                <template #trigger>
                  <n-button size="tiny" tertiary type="error">删除</n-button>
                </template>
                删除「{{ it.title }}」？
              </n-popconfirm>
            </span>
          </div>
          <div v-if="it.body_md" class="prose mt-2 max-h-96 overflow-y-auto border-t border-line pt-2 text-sm"
               v-html="bodies.get(it.id)" />
        </li>
      </ul>
    </div>

    <n-modal :show="show" preset="card" :title="edit?.id == null ? '新建公告' : '编辑公告'"
             style="width: min(640px, calc(100vw - 48px))" @update:show="(v: boolean) => show = v">
      <div v-if="edit" class="space-y-3">
        <n-input v-model:value="edit.title" placeholder="标题（一行）" maxlength="200" show-count />
        <div class="flex items-center gap-2">
          <span class="text-xs text-ink-3">发布日期</span>
          <n-date-picker v-model:formatted-value="edit.date" value-format="yyyy-MM-dd"
                         type="date" size="small" clearable style="width: 160px" />
          <span class="text-xs text-ink-3">留空 = 存草稿</span>
          <div class="ml-auto flex gap-1">
            <button v-for="m in (['edit', 'preview'] as const)" :key="m"
                    class="px-2 py-1 text-xs"
                    :class="mode === m ? 'bg-elevated text-brand' : 'text-ink-3 hover:text-ink'"
                    @click="mode = m">{{ m === 'edit' ? '编辑' : '预览' }}</button>
          </div>
        </div>
        <n-input v-if="mode === 'edit'" v-model:value="edit.body_md" type="textarea" :rows="10"
                 placeholder="正文（Markdown，支持表格/代码块/标题）" />
        <div v-else class="prose max-h-[40vh] min-h-[180px] overflow-y-auto  border border-line p-3"
             v-html="previewHtml" />
        <div class="flex justify-end gap-2">
          <n-button size="small" tertiary @click="show = false">取消</n-button>
          <n-button size="small" type="primary" :loading="saving" @click="save">保存</n-button>
        </div>
      </div>
    </n-modal>
  </div>
</template>
