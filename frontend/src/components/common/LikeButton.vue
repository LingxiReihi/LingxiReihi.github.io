<script setup lang="ts">
import { ref } from 'vue'

import { modelsApi, postsApi } from '@/api'

const props = defineProps<{ type: 'article' | 'model'; slug: string; initial: number }>()

const liked = ref(false)
const count = ref(props.initial)
const busy = ref(false)
const errMsg = ref('')
const storageKey = `liked:${props.type}:${props.slug}`

// localStorage 仅客户端访问（SSR 安全）；刷新后保持已赞态
function restore() {
  liked.value = localStorage.getItem(storageKey) === '1'
}

async function toggle() {
  if (busy.value) return
  busy.value = true
  errMsg.value = ''
  const wasLiked = liked.value
  try {
    const api = props.type === 'article' ? postsApi : modelsApi
    const d = wasLiked ? await api.unlike(props.slug) : await api.like(props.slug)
    count.value = d.likes
    liked.value = !wasLiked
    if (liked.value) localStorage.setItem(storageKey, '1')
    else localStorage.removeItem(storageKey)
  } catch (e: any) {
    errMsg.value = e?.message || (wasLiked ? '取消点赞失败' : '点赞失败')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <span class="inline-flex items-center gap-2">
    <button
      class="rounded-lg border px-4 py-2 text-sm transition-colors"
      :class="liked ? 'border-brand/50 bg-brand/10 text-brand hover:opacity-80' : 'border-line text-ink-2 hover:border-brand hover:text-brand'"
      :disabled="busy" :aria-pressed="liked"
      :title="liked ? '再次点击取消点赞' : ''"
      @click="toggle" @vue:mounted="restore"
    >
      {{ liked ? '👍 已赞' : '👍 点赞' }} <span class="font-medium">{{ count }}</span>
    </button>
    <span v-if="errMsg" class="text-xs text-ink-3">{{ errMsg }}</span>
  </span>
</template>
