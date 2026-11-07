<script setup lang="ts">
import { postsApi } from '@/api'
import type { ContentOut, TagOut } from '@/api/types'
import ColumnNav from '@/components/site/ColumnNav.vue'
import ContentCard from '@/components/common/ContentCard.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorRetry from '@/components/common/ErrorRetry.vue'
import SkeletonBlock from '@/components/common/SkeletonBlock.vue'
import LineIcon from '@/components/common/LineIcon.vue'
import ListFooter from '@/components/site/ListFooter.vue'
import { useSeo } from '@/composables/useSeo'
import { useInfiniteScroll } from '@/composables/useInfiniteScroll'
import { useReveal } from '@/composables/useReveal'
import { useDebounceFn } from '@vueuse/core'
import { nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

useSeo({ title: '博客', path: '/blog' })
const { refresh: refreshReveal } = useReveal()

const route = useRoute()
const router = useRouter()

const items = ref<ContentOut[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(true)
const error = ref<string | null>(null)
const moreLoading = ref(false)
/** 追加一批失败：保留已加载内容，只在这一格提示重试 */
const moreFailed = ref(false)
const tags = ref<TagOut[]>([])
const kw = ref((route.query.q as string) || '')
// 标签多选：逗号分隔存 route.query.tag，AND 语义（同时包含所有所选标签）
const tagSel = ref<string[]>(((route.query.tag as string) || '').split(',').filter(Boolean))
// 栏目目录栏选中项（slug，null=全部），与 route.query.column 同步
const colSel = ref<string | null>((route.query.column as string) || null)
const PAGE_SIZE = 12

async function fetchPage(reset: boolean) {
  if (reset) { loading.value = true; page.value = 1; moreFailed.value = false } else moreLoading.value = true
  error.value = null
  try {
    const d = await postsApi.list({ q: kw.value || undefined, tag: tagSel.value.join(',') || undefined, column: colSel.value || undefined, page: page.value, page_size: PAGE_SIZE })
    items.value = reset ? d.items : [...items.value, ...d.items]
    total.value = d.total
  } catch (e: any) {
    if (reset) {
      error.value = e?.message || '加载失败'
      items.value = []
    } else {
      // 追加失败不推翻已有列表，回退页码以免跳过这一批
      page.value = Math.max(1, page.value - 1)
      moreFailed.value = true
    }
  } finally {
    loading.value = false
    moreLoading.value = false
    nextTick(() => refreshReveal())
    if (!error.value && !moreFailed.value) notifyLoaded()
  }
}

function syncQuery() {
  router.replace({ query: { ...(kw.value ? { q: kw.value } : {}), ...(tagSel.value.length ? { tag: tagSel.value.join(',') } : {}), ...(colSel.value ? { column: colSel.value } : {}) } })
}

const debouncedSearch = useDebounceFn(() => { syncQuery(); fetchPage(true) }, 300)

watch(kw, debouncedSearch)
watch(tagSel, () => { syncQuery(); fetchPage(true) }, { deep: true })
watch(colSel, () => { syncQuery(); fetchPage(true) })

function toggleTag(slug: string) {
  const i = tagSel.value.indexOf(slug)
  if (i >= 0) tagSel.value.splice(i, 1)
  else tagSel.value.push(slug)
}
function clearTags() { tagSel.value = [] }

/* ---------- 触底自动加载：每批固定 12 条（逻辑与模型/杂谈页共用同一 composable） ---------- */
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

onMounted(() => {
  postsApi.tags('article').then((d) => (tags.value = d.items)).catch(() => {})
  fetchPage(true)
})
</script>

<template>
  <div class="mx-auto max-w-6xl px-4 py-12">
    <p class="font-mono text-[10px] uppercase tracking-[0.24em] text-brand">// Blog</p>
    <h1 class="mt-3 text-3xl font-bold tracking-tight">博客</h1>

    <div class="mt-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:gap-8">
      <ColumnNav v-model="colSel" type="article" class="shrink-0 lg:w-52" />
      <div class="min-w-0 flex-1">
        <div>
          <input
            v-model="kw"
            type="search"
            placeholder="搜索标题 / 摘要 / 正文…"
            class="w-full max-w-sm border border-line bg-surface px-4 py-2 text-sm outline-none transition-colors placeholder:text-ink-3 focus:border-brand"
            aria-label="搜索文章"
          />
          <div v-if="tags.length" class="mt-4 flex flex-wrap gap-2">
            <button
              class="border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] transition-colors"
              :class="!tagSel.length ? 'border-brand bg-brand text-[#04110f]' : 'border-line text-ink-2 hover:border-brand/60 hover:text-brand'"
              @click="clearTags"
            >全部</button>
            <button
              v-for="t in tags.slice(0, 12)" :key="t.id"
              class="border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] transition-colors"
              :class="tagSel.includes(t.slug) ? 'border-brand bg-brand text-[#04110f]' : 'border-line text-ink-2 hover:border-brand/60 hover:text-brand'"
              @click="toggleTag(t.slug)"
            >{{ t.name }} <span class="opacity-60">{{ t.count }}</span></button>
          </div>
        </div>

        <div v-if="tagSel.length || kw || colSel" class="mt-4 flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-ink-3">
          <span>结果：{{ total }}</span>
          <button v-if="colSel" class="inline-flex items-center gap-1 border border-line px-2 py-0.5 transition-colors hover:border-brand hover:text-brand" @click="colSel = null"><LineIcon name="folder" :size="12" />{{ colSel }} ×</button>
          <button v-for="t in tagSel" :key="t" class="border border-line px-2 py-0.5 transition-colors hover:border-brand hover:text-brand" @click="toggleTag(t)">#{{ t }} ×</button>
          <button v-if="kw" class="border border-line px-2 py-0.5 transition-colors hover:border-brand hover:text-brand" @click="kw = ''">“{{ kw }}” ×</button>
        </div>

        <ErrorRetry v-if="error" :message="error" @retry="fetchPage(true)" class="mt-8" />
        <SkeletonBlock v-else-if="loading" :lines="4" height="10rem" class="mt-8" />
        <EmptyState
          v-else-if="!items.length"
          title="没有匹配的文章"
          hint="换个关键词或清除筛选试试"
          :cta-label="(kw || tagSel.length || colSel) ? '清除筛选' : ''"
          @action="kw = ''; clearTags(); colSel = null"
        />
        <template v-else>
          <div class="mt-8 columns-1 gap-5 sm:columns-2 xl:columns-3">
            <div v-for="p in items" :key="p.id" data-reveal class="mb-5 break-inside-avoid">
              <ContentCard :item="p" :to="`/blog/${p.slug}`" />
            </div>
          </div>
          <!-- 触底哨兵：滚动到这里前 300px 自动取下一批；按钮留作兜底与无障碍入口 -->
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
