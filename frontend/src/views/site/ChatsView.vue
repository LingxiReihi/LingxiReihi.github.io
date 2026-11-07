<script setup lang="ts">
import { chatsApi, postsApi } from '@/api'
import type { ContentOut, TagOut } from '@/api/types'
import ColumnNav from '@/components/site/ColumnNav.vue'
import ContentCard from '@/components/common/ContentCard.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorRetry from '@/components/common/ErrorRetry.vue'
import SkeletonBlock from '@/components/common/SkeletonBlock.vue'
import ListFooter from '@/components/site/ListFooter.vue'
import { useInfiniteScroll } from '@/composables/useInfiniteScroll'
import { useSeo } from '@/composables/useSeo'
import { useReveal } from '@/composables/useReveal'
import { nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

useSeo({ title: '杂谈', path: '/chats' })
const { refresh: refreshReveal } = useReveal()

const route = useRoute()
const router = useRouter()

const items = ref<ContentOut[]>([])
const loading = ref(true)
const moreLoading = ref(false)
/** 追加一批失败：保留已加载内容，只在底部提示重试 */
const moreFailed = ref(false)
const error = ref<string | null>(null)
const done = ref(false)
const cursor = ref<string | null>(null)
const tags = ref<TagOut[]>([])
// 标签多选（AND），与博客页一致
const tagSel = ref<string[]>(((route.query.tag as string) || '').split(',').filter(Boolean))
// 栏目目录栏选中项（slug，null=全部）
const colSel = ref<string | null>((route.query.column as string) || null)

async function load(reset = false) {
  if (reset) { cursor.value = null; done.value = false; items.value = []; moreFailed.value = false }
  if (reset) loading.value = true
  else moreLoading.value = true
  error.value = null
  try {
    const d = await chatsApi.list({ cursor: cursor.value ?? undefined, limit: 12, tag: tagSel.value.join(',') || undefined, column: colSel.value || undefined })
    items.value = [...items.value, ...d.items]
    cursor.value = d.next_cursor
    done.value = !d.next_cursor
  } catch (e: any) {
    if (reset) {
      error.value = e?.message || '加载失败'
      items.value = []
    } else {
      moreFailed.value = true        // 游标没推进，重试即续上同一批
    }
  } finally {
    loading.value = false
    moreLoading.value = false
    nextTick(() => refreshReveal())
    if (!error.value && !moreFailed.value) notifyLoaded()
  }
}

/* 触底加载：与博客/模型页同一套逻辑（游标分页，done 由 next_cursor 决定） */
const sentinel = ref<HTMLElement | null>(null)

function loadMore() {
  if (loading.value || moreLoading.value || done.value) return
  moreFailed.value = false
  load()
}

const { notifyLoaded } = useInfiniteScroll(sentinel, {
  canLoad: () => !loading.value && !moreLoading.value && !moreFailed.value && !done.value,
  load: loadMore,
})

function syncQuery() {
  router.replace({ query: { ...(tagSel.value.length ? { tag: tagSel.value.join(',') } : {}), ...(colSel.value ? { column: colSel.value } : {}) } })
}

watch(tagSel, () => { syncQuery(); load(true) }, { deep: true })
watch(colSel, () => { syncQuery(); load(true) })

function toggleTag(slug: string) {
  const i = tagSel.value.indexOf(slug)
  if (i >= 0) tagSel.value.splice(i, 1)
  else tagSel.value.push(slug)
}
function clearTags() { tagSel.value = [] }

load(true)
postsApi.tags('chat').then((d) => (tags.value = d.items.filter((t) => t.count))).catch(() => {})
</script>

<template>
  <div class="mx-auto max-w-6xl px-4 py-12">
    <h1 class="text-3xl font-bold">杂谈</h1>
    <p class="mt-2 text-sm text-ink-2">碎片想法与日常，点击查看全文</p>

    <div class="mt-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:gap-8">
      <ColumnNav v-model="colSel" type="chat" class="shrink-0 lg:w-52" />
      <div class="min-w-0 flex-1">
        <div v-if="tags.length" class="flex flex-wrap gap-2 text-sm">
          <button
            class="rounded-full border px-3 py-1 transition-colors"
            :class="!tagSel.length ? 'border-brand bg-brand/10 text-brand' : 'border-line text-ink-2 hover:bg-elevated'"
            @click="clearTags"
          >全部</button>
          <button
            v-for="t in tags.slice(0, 12)" :key="t.id"
            class="rounded-full border px-3 py-1 transition-colors"
            :class="tagSel.includes(t.slug) ? 'border-brand bg-brand/10 text-brand' : 'border-line text-ink-2 hover:bg-elevated'"
            @click="toggleTag(t.slug)"
          >{{ t.name }} <span class="opacity-60">{{ t.count }}</span></button>
        </div>

        <ErrorRetry v-if="error" :message="error" class="mt-8" @retry="load(true)" />
        <SkeletonBlock v-else-if="loading" :lines="4" height="7rem" class="mt-8" />
        <EmptyState
          v-else-if="!items.length"
          title="还没有杂谈"
          :hint="tagSel.length || colSel ? '该筛选下暂无内容' : '后台发布第一条吧'"
          :cta-label="tagSel.length || colSel ? '清除筛选' : ''"
          @action="clearTags(); colSel = null"
        />
        <template v-else>
          <div class="mt-8 columns-1 gap-5 sm:columns-2 lg:columns-3">
            <div v-for="c in items" :key="c.id" data-reveal class="mb-5 break-inside-avoid">
              <ContentCard :item="c" :to="`/chats/${c.id}`" />
            </div>
          </div>
          <!-- 触底哨兵：与博客/模型页同一套交互 -->
          <div ref="sentinel">
            <ListFooter
              :loading="moreLoading" :failed="moreFailed" :done="done"
              :loaded="items.length"
              @more="loadMore" @retry="loadMore"
            />
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
