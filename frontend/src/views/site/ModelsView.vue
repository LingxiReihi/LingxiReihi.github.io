<script setup lang="ts">
import { modelsApi } from '@/api'
import type { ContentOut } from '@/api/types'
import ColumnNav from '@/components/site/ColumnNav.vue'
import ErrorRetry from '@/components/common/ErrorRetry.vue'
import SkeletonBlock from '@/components/common/SkeletonBlock.vue'
import LineIcon from '@/components/common/LineIcon.vue'
import ListFooter from '@/components/site/ListFooter.vue'
import { useInfiniteScroll } from '@/composables/useInfiniteScroll'
import { useSeo } from '@/composables/useSeo'
import { useReveal } from '@/composables/useReveal'
import { useRoute, useRouter } from 'vue-router'
import { nextTick, onMounted, ref, watch } from 'vue'

useSeo({ title: '模型作品', path: '/models' })
const { refresh: refreshReveal } = useReveal()

const KINDS = [
  { key: 'all', label: '全部' },
  { key: '3d', label: '3D 模型' },
  { key: 'render', label: '渲染图' },
  { key: 'animation', label: '动画' },
] as const

const route = useRoute()
const router = useRouter()
const kind = ref((route.query.kind as string) || 'all')
// 标签筛选：详情页标签链入 /models?tag=slug（逗号分隔多选），无独立 pills UI
const tag = ref((route.query.tag as string) || '')
// 栏目目录栏选中项（slug，null=全部）
const colSel = ref<string | null>((route.query.column as string) || null)

const PAGE_SIZE = 12
const items = ref<ContentOut[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(true)
const moreLoading = ref(false)
/** 追加一批失败：保留已加载内容，只在底部提示重试 */
const moreFailed = ref(false)
const error = ref<string | null>(null)

async function fetchPage(reset: boolean) {
  if (reset) { loading.value = true; page.value = 1; moreFailed.value = false } else moreLoading.value = true
  error.value = null
  try {
    const d = await modelsApi.list({
      kind: kind.value, tag: tag.value || undefined, column: colSel.value || undefined,
      page: page.value, page_size: PAGE_SIZE,
    })
    items.value = reset ? d.items : [...items.value, ...d.items]
    total.value = d.total
  } catch (e: any) {
    if (reset) {
      error.value = e?.message || '加载失败'
      items.value = []
    } else {
      page.value = Math.max(1, page.value - 1)   // 回退页码，避免跳过这一批
      moreFailed.value = true
    }
  } finally {
    loading.value = false
    moreLoading.value = false
    nextTick(() => refreshReveal())
    if (!error.value && !moreFailed.value) notifyLoaded()
  }
}

/* 触底加载：与博客/杂谈页同一套逻辑 */
const sentinel = ref<HTMLElement | null>(null)

function loadMore() {
  if (loading.value || moreLoading.value) return
  if (items.value.length >= total.value) return
  moreFailed.value = false
  page.value += 1
  fetchPage(false)
}

const { notifyLoaded } = useInfiniteScroll(sentinel, {
  canLoad: () => !loading.value && !moreLoading.value && !moreFailed.value
    && items.value.length < total.value,
  load: loadMore,
})

function syncQuery() {
  router.replace({ query: { ...(kind.value === 'all' ? {} : { kind: kind.value }), ...(tag.value ? { tag: tag.value } : {}), ...(colSel.value ? { column: colSel.value } : {}) } })
}

watch(kind, () => { syncQuery(); fetchPage(true) })
watch(tag, () => { syncQuery(); fetchPage(true) })
watch(colSel, () => { syncQuery(); fetchPage(true) })
onMounted(() => fetchPage(true))

function kindLabel(k?: string | null) {
  return KINDS.find((x) => x.key === k)?.label ?? '作品'
}
</script>

<template>
  <div class="mx-auto max-w-6xl px-4 py-12">
    <h1 class="text-3xl font-bold">模型作品</h1>
    <p class="mt-2 text-sm text-ink-2">Blender 3D 模型 · 渲染图 · 动画</p>

    <div class="mt-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:gap-8">
      <ColumnNav v-model="colSel" type="model" class="shrink-0 lg:w-52" />
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap gap-2" role="tablist" aria-label="作品类型">
          <button
            v-for="k in KINDS" :key="k.key"
            role="tab" :aria-selected="kind === k.key"
            class="rounded-lg border px-4 py-1.5 text-sm transition-colors"
            :class="kind === k.key ? 'border-brand bg-brand/10 text-brand font-medium' : 'border-line text-ink-2 hover:bg-elevated'"
            @click="kind = k.key"
          >{{ k.label }}</button>
        </div>

        <div v-if="tag || colSel" class="mt-4 flex flex-wrap items-center gap-2 text-sm text-ink-3">
          <span v-if="colSel">栏目：
            <button class="inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 transition-colors hover:border-brand hover:text-brand" @click="colSel = null"><LineIcon name="folder" :size="12" />{{ colSel }} ×</button>
          </span>
          <span v-if="tag">标签筛选：</span>
          <button
            v-for="t in tag.split(',').filter(Boolean)" :key="t"
            class="rounded-full border border-line px-2 py-0.5 transition-colors hover:border-brand hover:text-brand"
            @click="tag = tag.split(',').filter(x => x !== t).join(',')"
          >#{{ t }} ×</button>
        </div>

        <ErrorRetry v-if="error" :message="error" @retry="fetchPage(true)" class="mt-8" />
        <SkeletonBlock v-else-if="loading" :lines="5" height="12rem" class="mt-8" />
        <div v-else-if="!items.length" class="py-20 text-center text-ink-3">该分类下暂无作品</div>
        <template v-else>
        <!-- 瀑布流（CSS columns） -->
        <div class="mt-8 gap-4 [column-fill:_balance] sm:columns-2 lg:columns-3">
      <RouterLink
        v-for="m in items" :key="m.id"
        :to="`/models/${m.slug}`"
        data-reveal
        class="group mb-4 block break-inside-avoid overflow-hidden rounded-xl border border-line bg-surface transition-all hover:-translate-y-0.5 hover:border-brand/40"
      >
        <div class="relative overflow-hidden">
          <img
            v-if="m.cover" :src="m.cover" :alt="m.title" loading="lazy"
            class="w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
            :class="m.media_kind === 'render' ? 'aspect-[3/4]' : 'aspect-square'"
          />
          <div v-else class="flex aspect-square w-full items-center justify-center bg-elevated text-ink-3"><LineIcon name="cube" :size="40" /></div>
          <span class="absolute left-2 top-2 rounded-full bg-black/60 px-2 py-0.5 text-xs text-white backdrop-blur">{{ kindLabel(m.media_kind) }}</span>
        </div>
        <div class="p-4">
          <p class="truncate font-medium group-hover:text-brand">{{ m.title }}</p>
          <p v-if="m.summary" class="mt-1 line-clamp-1 text-xs text-ink-3">{{ m.summary }}</p>
        </div>
      </RouterLink>
        </div>
        <!-- 触底哨兵：与博客/杂谈页同一套交互 -->
        <div ref="sentinel">
          <ListFooter
            :loading="moreLoading" :failed="moreFailed" :done="items.length >= total"
            :loaded="items.length" :total="total"
            @more="loadMore" @retry="loadMore"
          />
        </div>
        </template>
      </div>
    </div>
  </div>
</template>
