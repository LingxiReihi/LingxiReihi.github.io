<script setup lang="ts">
import type { MediaAsset, MediaCategory } from '@/api/types'
import {
  NButton, NImage, NInput, NModal, NPopconfirm, NSelect, NSpin, NUpload, useMessage,
} from 'naive-ui'
import { computed, onMounted, reactive, ref } from 'vue'

import { adminMediaApi } from '@/api'
import type { MediaGroup } from '@/api'
import { MEDIA_CATEGORIES, mediaCategoryLabel } from '@/api/types'
import AdminIcon from '@/components/admin/AdminIcon.vue'
import { useAuthStore } from '@/stores/auth'
import { formatSize } from '@/utils/format'

const auth = useAuthStore()
const message = useMessage()

const items = ref<MediaAsset[]>([])
const total = ref(0)
const page = ref(1)
const size = 24
const loading = ref(true)
const q = ref('')

/* ---------- 左：分类 ---------- */
type CatFilter = MediaCategory | 'all' | 'none'
const cat = ref<CatFilter>('all')
const catOptions = [
  { label: '全部分类', value: 'all' },
  ...MEDIA_CATEGORIES.map((c) => ({ label: c.label, value: c.value as string })),
  { label: '未分类', value: 'none' },
]

/* ---------- 右：内容（自动分组，来自实际引用关系） ---------- */
type ContentFilter = 'all' | 'none' | number
const contentFilter = ref<ContentFilter>('all')
const groups = ref<MediaGroup[]>([])
const unusedCount = ref(0)
const contentOptions = computed(() => [
  { label: '全部内容', value: 'all' as string | number },
  { label: `未被引用（${unusedCount.value}）`, value: 'none' as string | number },
  ...groups.value.map((g) => ({ label: `${g.title}（${g.count}）`, value: g.id as string | number })),
])

const uploadCat = ref<MediaCategory>('blog')
const uploadCatOptions = MEDIA_CATEGORIES.map((c) => ({ label: c.label, value: c.value }))

async function loadGroups() {
  try {
    const d = await adminMediaApi.contents()
    groups.value = d.items
    unusedCount.value = d.unused
  } catch { /* 非关键：下拉为空不影响列表 */ }
}

async function load() {
  loading.value = true
  try {
    const d = await adminMediaApi.list({
      q: q.value || undefined,
      category: cat.value === 'all' ? undefined : cat.value,
      content_id: typeof contentFilter.value === 'number' ? contentFilter.value : undefined,
      unused: contentFilter.value === 'none' ? 1 : undefined,
      page: page.value, page_size: size,
    })
    items.value = d.items
    total.value = d.total
  } catch (e: any) {
    message.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => { load(); loadGroups() })

function applyFilter() {
  page.value = 1
  checked.value = []
  load()
}

/* ---------- 多选批量改分类 ---------- */
const selectMode = ref(false)
const checked = ref<number[]>([])
const targetCat = ref<MediaCategory>('blog')
const allChecked = computed(() =>
  items.value.length > 0 && items.value.every((a) => checked.value.includes(a.id)))

function toggle(a: MediaAsset) {
  const i = checked.value.indexOf(a.id)
  if (i >= 0) checked.value.splice(i, 1)
  else checked.value.push(a.id)
}
function toggleAll() {
  checked.value = allChecked.value ? [] : items.value.map((a) => a.id)
}

async function applyCategorize() {
  if (!checked.value.length) { message.warning('请先勾选素材'); return }
  try {
    const d = await adminMediaApi.categorize(checked.value, targetCat.value)
    message.success(`已改分类 ${d.updated} 项${d.denied?.length ? `，${d.denied.length} 项非你上传已跳过` : ''}`)
    checked.value = []
    await Promise.all([load(), loadGroups()])
  } catch (e: any) {
    message.error(e?.message || '改分类失败')
  }
}

/* ---------- 单张编辑：重命名 + 换分类（都不动 URL） ---------- */
const editing = ref<MediaAsset | null>(null)
const editForm = reactive({ filename: '', category: 'blog' as MediaCategory })
const editSaving = ref(false)

function openEdit(a: MediaAsset) {
  editing.value = a
  editForm.filename = a.filename ?? ''
  editForm.category = (a.category ?? 'blog') as MediaCategory
}

async function saveEdit() {
  const a = editing.value
  if (!a || editSaving.value) return
  const name = editForm.filename.trim()
  if (!name) { message.warning('文件名不能为空'); return }
  editSaving.value = true
  try {
    if (name !== a.filename) await adminMediaApi.rename(a.id, name)
    if (editForm.category !== a.category) await adminMediaApi.categorize([a.id], editForm.category)
    editing.value = null
    message.success('已保存，链接地址未变，已有引用照常有效')
    await Promise.all([load(), loadGroups()])
  } catch (e: any) {
    message.error(e?.message || '保存失败')
  } finally {
    editSaving.value = false
  }
}

async function onUpload({ file, onFinish, onError }: any) {
  try {
    await adminMediaApi.upload(file.file as File, uploadCat.value)
    onFinish()
    page.value = 1
    await Promise.all([load(), loadGroups()])
    message.success(`上传成功（${mediaCategoryLabel(uploadCat.value)}）`)
  } catch (e: any) {
    onError(e)
    message.error(e?.message || '上传失败')
  }
}

async function remove(a: MediaAsset) {
  try {
    await adminMediaApi.remove(a.id)
    message.success('已删除素材记录')
    await Promise.all([load(), loadGroups()])
  } catch (e: any) {
    // 被内容引用时服务端会带出具体篇名，直接透传
    message.error(e?.message || '删除失败')
  }
}

const usedLabel = (a: MediaAsset) => {
  const u = a.used_by ?? []
  if (!u.length) return '未被引用'
  return u.length === 1 ? `用于《${u[0].title}》` : `用于《${u[0].title}》等 ${u.length} 篇`
}
</script>

<template>
  <div>
    <div class="mb-3 flex flex-wrap items-center gap-3">
      <h1 class="text-2xl font-bold">素材库</h1>
      <span class="font-mono text-[11px] text-ink-3">{{ total }} 项</span>
      <div class="ml-auto flex items-center gap-2">
        <n-input
          v-model:value="q" size="small" placeholder="搜索文件名" clearable class="!w-40"
          @keyup.enter="applyFilter" @clear="applyFilter"
        />
        <n-select v-model:value="uploadCat" size="small" :options="uploadCatOptions" class="!w-28" />
        <n-upload v-if="auth.can('media:write')" :custom-request="onUpload" :show-file-list="false" multiple>
          <n-button size="small" type="primary">上传</n-button>
        </n-upload>
        <n-button size="small" :type="selectMode ? 'primary' : 'default'" quaternary @click="selectMode = !selectMode; checked = []">
          {{ selectMode ? '退出多选' : '多选' }}
        </n-button>
      </div>
    </div>

    <!-- 左类别 / 右内容 两级筛选 -->
    <div class="mb-4 flex flex-wrap items-center gap-3 border border-line bg-surface px-3 py-2">
      <div class="flex items-center gap-2">
        <span class="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">分类</span>
        <n-select v-model:value="cat" size="small" :options="catOptions" class="!w-32" @update:value="applyFilter" />
      </div>
      <div class="flex items-center gap-2">
        <span class="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">内容</span>
        <n-select
          v-model:value="contentFilter" size="small" filterable :options="contentOptions"
          class="!w-64" placeholder="全部内容" @update:value="applyFilter"
        />
      </div>
      <template v-if="selectMode">
        <span class="ml-2 font-mono text-[11px] text-ink-3">已选 {{ checked.length }} 项</span>
        <label class="flex cursor-pointer items-center gap-1 text-xs text-ink-2">
          <input type="checkbox" :checked="allChecked" @change="toggleAll"> 本页全选
        </label>
        <n-select v-model:value="targetCat" size="tiny" :options="uploadCatOptions" class="!w-28" />
        <n-button v-if="auth.can('media:write')" size="tiny" type="primary" :disabled="!checked.length" @click="applyCategorize">
          改分类
        </n-button>
      </template>
      <span class="ml-auto font-mono text-[10px] text-ink-3">改名/换分类都不会改变图片地址</span>
    </div>

    <n-spin :show="loading">
      <div v-if="items.length" class="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
        <div
          v-for="a in items" :key="a.id"
          class="group relative overflow-hidden border border-line bg-surface"
          :class="selectMode && checked.includes(a.id) ? 'ring-2 ring-brand' : ''"
        >
          <div class="relative aspect-video bg-elevated">
            <n-image v-if="a.kind === 'image'" :src="a.thumb || a.url" object-fit="cover" class="h-full w-full" :img-props="{ loading: 'lazy' }" />
            <div v-else class="flex h-full flex-col items-center justify-center text-ink-3">
              <AdminIcon :name="a.kind === 'model3d' ? 'cube' : a.kind === 'video' ? 'video' : 'doc'" :size="34" class="text-ink-3" />
            </div>
            <button
              v-if="selectMode" class="absolute left-2 top-2 bg-black/60 p-1" role="checkbox"
              :aria-checked="checked.includes(a.id)" @click="toggle(a)"
            >
              <span class="block h-4 w-4 border border-white" :class="checked.includes(a.id) ? 'bg-brand' : ''">{{ checked.includes(a.id) ? '✓' : '' }}</span>
            </button>
            <div v-else class="absolute right-2 top-2 hidden gap-1 group-hover:flex">
              <button class="bg-black/70 px-2 py-1 text-xs text-white hover:text-brand" @click="openEdit(a)">编辑</button>
              <n-popconfirm v-if="a.can_delete !== false" @positive-click="remove(a)">
                <template #trigger>
                  <button class="bg-black/70 px-2 py-1 text-xs text-white hover:text-danger">删除</button>
                </template>
                删除该素材记录？仍被内容引用时会阻止。
              </n-popconfirm>
            </div>
          </div>
          <div class="p-3 text-xs">
            <p class="truncate font-medium" :title="a.filename">{{ a.filename }}</p>
            <p class="mt-1 flex items-center gap-2 text-ink-3">
              <span class="bg-elevated px-1.5 py-0.5">{{ mediaCategoryLabel(a.category) }}</span>
              {{ formatSize(a.size) }}
              <span v-if="a.width"> · {{ a.width }}×{{ a.height }}</span>
            </p>
            <p
              class="mt-1 truncate" :class="a.used_by?.length ? 'text-ink-2' : 'text-ink-3'"
              :title="(a.used_by ?? []).map((u) => u.title).join('\n') || '未被引用'"
            >{{ usedLabel(a) }}</p>
          </div>
        </div>
      </div>
      <p v-else-if="!loading" class="py-20 text-center text-sm text-ink-3">没有符合条件的素材</p>
    </n-spin>

    <div v-if="total > size" class="mt-6 flex justify-center gap-2 text-sm">
      <n-button size="small" :disabled="page <= 1" @click="page--; load()">上一页</n-button>
      <span class="py-1 text-ink-3">{{ page }} / {{ Math.ceil(total / size) }}</span>
      <n-button size="small" :disabled="page >= Math.ceil(total / size)" @click="page++; load()">下一页</n-button>
    </div>

    <!-- 单张编辑：改名 + 换分类，两者都不影响图片地址 -->
    <n-modal
      :show="!!editing" preset="card" title="编辑素材"
      style="width: 420px; max-width: 94vw"
      @update:show="(v: boolean) => { if (!v) editing = null }"
    >
      <div class="space-y-3">
        <div>
          <p class="mb-1 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">文件名</p>
          <n-input v-model:value="editForm.filename" placeholder="给这张图起个名字" @keyup.enter="saveEdit" />
        </div>
        <div>
          <p class="mb-1 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">分类</p>
          <n-select v-model:value="editForm.category" :options="uploadCatOptions" />
        </div>
        <p class="font-mono text-[10px] leading-relaxed text-ink-3">
          地址 {{ editing?.url }} 保持不变 —— 改名与换分类只动标签，历史正文、封面与外部分享都不受影响。
        </p>
      </div>
      <div class="mt-4 flex justify-end gap-2">
        <n-button size="small" @click="editing = null">取消</n-button>
        <n-button size="small" type="primary" :loading="editSaving" @click="saveEdit">保存</n-button>
      </div>
    </n-modal>
  </div>
</template>
