<script setup lang="ts">
import { modelsApi } from '@/api'
import ErrorRetry from '@/components/common/ErrorRetry.vue'
import Lightbox from '@/components/site/Lightbox.vue'
import MediaViewer from '@/components/site/MediaViewer.vue'
import SkeletonBlock from '@/components/common/SkeletonBlock.vue'
import { useAsync } from '@/composables/useAsync'
import { enhanceCodeBlocks } from '@/composables/useCodeEnhance'
import { renderMd } from '@/composables/useMd'
import { useSeo } from '@/composables/useSeo'
import { assetKindLabel, isZip } from '@/utils/media3d'
import { formatDate, formatSize } from '@/utils/format'
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const slug = computed(() => String(route.params.slug))
const state = useAsync(() => modelsApi.detail(slug.value), `model:${slug.value}`)
const proseRef = ref<HTMLElement | null>(null)

const html = computed(() => (state.data.value ? renderMd(state.data.value.body_md).html : ''))
watch(html, (v) => { if (v) nextTick(() => proseRef.value && enhanceCodeBlocks(proseRef.value)) })
const images = computed(() => (state.data.value?.assets ?? []).filter((a) => a.kind === 'image'))
const links = computed<{ label: string; url: string }[]>(
  () => (state.data.value?.extra?.links as { label: string; url: string }[] | undefined) ?? [])
const fileAssets = computed(() => (state.data.value?.assets ?? []).filter((a) => a.kind === 'model3d' || a.kind === 'video'))
const lightbox = ref<number | null>(null)
const downloading = ref(false)

const d = () => state.data.value
useSeo({
  title: computed(() => d()?.title ?? '模型'),
  description: computed(() => d()?.summary),
  path: computed(() => `/models/${slug.value}`),
  image: computed(() => d()?.cover),
  jsonLd: computed(() => {
    const c = d()
    if (!c) return undefined
    return {
      '@context': 'https://schema.org', '@type': 'CreativeWork',
      name: c.title, description: c.summary, datePublished: c.published_at,
      creator: { '@type': 'Person', name: c.extra?.author ?? '' },
    }
  }),
})

watch(slug, () => state.retry())

async function downloadAsset(a: { id: number; filename?: string; storage_key?: string }) {
  downloading.value = true
  try {
    const r = await modelsApi.download(slug.value, a.id)
    window.open(r.url, '_blank')
  } finally {
    downloading.value = false
  }
}

</script>

<template>
  <div>
    <ErrorRetry v-if="state.error.value" :message="state.error.value" @retry="state.retry" />
    <SkeletonBlock v-else-if="state.loading.value" :lines="6" height="14rem" class="mx-auto max-w-5xl px-4 py-12" />
    <template v-else-if="state.data.value">
      <div class="mx-auto grid max-w-6xl gap-10 px-4 py-12 lg:grid-cols-[1.5fr_1fr]">
        <div>
          <MediaViewer :assets="state.data.value.assets" :media-kind="state.data.value.media_kind" @preview="lightbox = $event" />
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div ref="proseRef" class="prose mt-8" v-html="html" />
        </div>
        <aside>
          <nav class="mb-4 text-xs text-ink-3" aria-label="面包屑">
            <RouterLink to="/models" class="hover:text-brand">模型作品</RouterLink> / <span>{{ state.data.value.title }}</span>
          </nav>
          <h1 class="text-2xl font-bold leading-snug">{{ state.data.value.title }}</h1>
          <p v-if="state.data.value.summary" class="mt-2 text-sm text-ink-2">{{ state.data.value.summary }}</p>
          <dl class="mt-6 divide-y divide-line rounded-xl border border-line bg-surface px-5 text-sm">
            <div class="flex justify-between py-3">
              <dt class="text-ink-3">类型</dt>
              <dd>{{ state.data.value.media_kind === '3d' ? '3D 模型' : state.data.value.media_kind === 'render' ? '渲染图' : '动画' }}</dd>
            </div>
            <div v-if="state.data.value.author?.nickname" class="flex justify-between py-3">
              <dt class="text-ink-3">作者</dt>
              <dd>
                <RouterLink
                  :to="{ path: '/about', query: { a: state.data.value.author.nickname } }"
                  title="查看这位管理员的介绍"
                  class="flex items-center gap-1.5 transition-colors hover:text-brand"
                >
                  <img
                    v-if="state.data.value.author.avatar" :src="state.data.value.author.avatar" alt=""
                    class="h-5 w-5 rounded-full border border-line object-cover"
                  >{{ state.data.value.author.nickname }}
                </RouterLink>
              </dd>
            </div>
            <div class="flex justify-between py-3">
              <dt class="text-ink-3">发布</dt>
              <dd>{{ formatDate(state.data.value.published_at) }}</dd>
            </div>
            <div v-if="state.data.value.updated_at" class="flex justify-between py-3">
              <dt class="text-ink-3">更新</dt>
              <dd>{{ formatDate(state.data.value.updated_at) }}</dd>
            </div>
            <div v-for="a in fileAssets" :key="'s'+a.id" class="flex justify-between py-3">
              <dt class="text-ink-3">{{ assetKindLabel(a) }}体积</dt>
              <dd>{{ formatSize(a.size) }}<template v-if="isZip(a) && a.entries?.length"> · {{ a.entries.length }} 个文件</template></dd>
            </div>
          </dl>

          <div class="mt-5 flex flex-wrap gap-3">
            <button
              v-for="a in fileAssets" :key="a.id"
              class="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-black hover:opacity-90 disabled:opacity-50"
              :disabled="downloading"
              @click="downloadAsset(a)"
            >{{ downloading ? '准备中…' : `⬇ 下载 ${assetKindLabel(a)}${isZip(a) && a.entries?.length ? `（${a.entries.length} 个文件）` : ''}` }}</button>
            <a
              v-for="(l, i) in links" :key="i"
              :href="l.url" target="_blank" rel="noopener"
              class="rounded-lg border border-line px-4 py-2 text-sm text-ink-2 hover:bg-elevated"
            >{{ l.label }} ↗</a>
          </div>
          <div class="mt-6 flex flex-wrap gap-2 text-xs">
            <RouterLink
              v-for="t in state.data.value.tags" :key="t.id"
              :to="`/models?tag=${encodeURIComponent(t.slug)}`"
              class="rounded-full border border-line px-2 py-0.5 text-ink-3 transition-colors hover:border-brand hover:text-brand"
            >{{ t.name }}</RouterLink>
          </div>
        </aside>
      </div>

      <Lightbox
        v-if="lightbox !== null && images.length"
        :images="images.map(i => i.url)"
        :start="0"
        v-model:index="lightbox"
        @close="lightbox = null"
      />
    </template>
  </div>
</template>
