<script setup lang="ts">
/** 列表底部状态条：三个列表页（博客/模型/杂谈）共用，保证「加载中 / 失败重试 / 到底了」
 *  的措辞与样式一致。按钮同时是触底加载的兜底与无障碍入口。 */
withDefaults(defineProps<{
  loading?: boolean
  failed?: boolean
  done?: boolean
  loaded?: number
  /** 传了就显示「已显示全部 N 篇」，不传显示「— 到底了 —」 */
  total?: number | null
}>(), { loading: false, failed: false, done: false, loaded: 0, total: null })

const emit = defineEmits<{ (e: 'more'): void; (e: 'retry'): void }>()
</script>

<template>
  <div data-sentinel class="mt-8 text-center">
    <p v-if="loading" class="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-3">
      加载中…
    </p>
    <button
      v-else-if="failed"
      class="border border-danger/60 px-6 py-2 font-mono text-[11px] uppercase tracking-[0.16em] text-danger transition-colors hover:bg-danger/10"
      @click="emit('retry')"
    >加载失败，点击重试</button>
    <p v-else-if="done" class="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-3">
      {{ total != null ? `已显示全部 ${total} 篇` : '— 到底了 —' }}
    </p>
    <button
      v-else
      class="border border-line px-6 py-2 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-2 transition-colors hover:border-brand hover:text-brand"
      @click="emit('more')"
    >继续加载<template v-if="total != null">（{{ loaded }}/{{ total }}）</template></button>
  </div>
</template>
