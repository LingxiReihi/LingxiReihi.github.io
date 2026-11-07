<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { aboutApi } from '@/api'
import ErrorRetry from '@/components/common/ErrorRetry.vue'
import SkeletonBlock from '@/components/common/SkeletonBlock.vue'
import ProfileCard from '@/components/site/ProfileCard.vue'
import { useAsync } from '@/composables/useAsync'
import { useSeo } from '@/composables/useSeo'

const state = useAsync(() => aboutApi.get(), 'about')
const route = useRoute()

useSeo({
  title: '关于',
  description: computed(() => (state.data.value?.signature ?? '').slice(0, 80)),
  path: '/about',
})

const team = computed(() => state.data.value?.team ?? [])

/**
 * 内容页署名点进来时靠 ?a=<昵称> 定位到那张卡并短暂描边。
 * 用昵称而不是账号 ID：昵称本来就显示在页面上，不必为深链新开一项公开标识，
 * 也就不会把账号数量与创建顺序泄露出去。重名时命中第一张。
 */
const highlight = ref('')

async function focusTarget() {
  const name = typeof route.query.a === 'string' ? route.query.a : ''
  if (!name || typeof document === 'undefined') return
  await nextTick()
  const el = document.querySelector<HTMLElement>(`[data-author="${CSS.escape(name)}"]`)
  if (!el) return
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  el.scrollIntoView({ behavior: reduced ? 'instant' : 'smooth', block: 'start' })
  highlight.value = name
  window.setTimeout(() => { if (highlight.value === name) highlight.value = '' }, 1600)
}

watch(() => state.loading.value, (l) => { if (!l) void focusTarget() })
onMounted(() => { if (!state.loading.value) void focusTarget() })
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-6 px-4 py-12">
    <ErrorRetry v-if="state.error.value" :message="state.error.value" @retry="state.retry" />
    <SkeletonBlock v-else-if="state.loading.value" :lines="6" />
    <!-- 一行一张卡片：主体（顶级管理员）在最上，其余在职管理员同款布局依次排开 -->
    <template v-else-if="state.data.value">
      <ProfileCard :profile="state.data.value" host :highlighted="highlight === state.data.value.nickname" />
      <ProfileCard
        v-for="(m, i) in team" :key="i" :profile="m"
        :highlighted="highlight === m.nickname"
      />
    </template>
  </div>
</template>
