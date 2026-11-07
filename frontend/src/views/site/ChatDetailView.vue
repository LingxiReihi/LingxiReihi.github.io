<script setup lang="ts">
import { chatsApi } from '@/api'
import ErrorRetry from '@/components/common/ErrorRetry.vue'
import SkeletonBlock from '@/components/common/SkeletonBlock.vue'
import { useAsync } from '@/composables/useAsync'
import { enhanceCodeBlocks } from '@/composables/useCodeEnhance'
import { renderMd } from '@/composables/useMd'
import { useSeo } from '@/composables/useSeo'
import { formatDateTime } from '@/utils/format'
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const id = computed(() => Number(route.params.id))
const state = useAsync(() => chatsApi.detail(id.value), `chat:${id.value}`)
const proseRef = ref<HTMLElement | null>(null)

useSeo({
  title: computed(() => state.data.value?.title ?? '杂谈'),
  description: computed(() => (state.data.value?.body_md ?? '').slice(0, 80)),
  path: computed(() => `/chats/${id.value}`),
  image: computed(() => state.data.value?.cover),
})

const html = computed(() => (state.data.value ? renderMd(state.data.value.body_md).html : ''))
watch(html, (v) => { if (v) nextTick(() => proseRef.value && enhanceCodeBlocks(proseRef.value)) })
</script>

<template>
  <div class="mx-auto max-w-[640px] px-4 py-12">
    <ErrorRetry v-if="state.error.value" :message="state.error.value" @retry="state.retry" />
    <SkeletonBlock v-else-if="state.loading.value" :lines="4" />
    <article v-else-if="state.data.value">
      <RouterLink to="/chats" class="text-sm text-ink-3 hover:text-brand">← 杂谈列表</RouterLink>
      <h1 class="mt-4 text-2xl font-bold leading-snug">{{ state.data.value.title }}</h1>
      <p class="mt-2 flex flex-wrap items-center gap-2 text-sm text-ink-3">
        <RouterLink
          v-if="state.data.value.author?.nickname"
          :to="{ path: '/about', query: { a: state.data.value.author.nickname } }"
          title="查看这位管理员的介绍"
          class="flex items-center gap-1.5 transition-colors hover:text-brand"
        >
          <img
            v-if="state.data.value.author.avatar" :src="state.data.value.author.avatar" alt=""
            class="h-5 w-5 rounded-full border border-line object-cover"
          >{{ state.data.value.author.nickname }}
          <span>·</span>
        </RouterLink>
        {{ formatDateTime(state.data.value.published_at) }}
      </p>
      <img
        v-if="state.data.value.cover" :src="state.data.value.cover" :alt="state.data.value.title"
        class="mt-4 w-full rounded-xl border border-line"
      />
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div ref="proseRef" class="prose mt-3" v-html="html" />
    </article>
  </div>
</template>
