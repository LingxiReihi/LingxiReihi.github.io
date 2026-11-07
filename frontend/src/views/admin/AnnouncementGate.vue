<script setup lang="ts">
import { NModal, useMessage } from 'naive-ui'
import { computed, nextTick, ref, watch } from 'vue'

import { adminAnnouncementsApi } from '@/api'
import type { Announcement } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { renderMd } from '@/composables/useMd'

const message = useMessage()
const auth = useAuthStore()
const items = ref<Announcement[]>([])
const show = ref(false)
const confirmBtn = ref<HTMLButtonElement | null>(null)
let fetched = false      // 一次登录只拉一次：路由来回切不重复打扰
let reported = false     // × / 遮罩 / 「我知道了」可能重复走到 onClose：只上报一次

const bodies = computed(() => new Map(items.value.map((i) => [i.id, renderMd(i.body_md).html])))
const fmtDate = (iso: string | null) => (iso ? iso.slice(0, 10) : '')

async function pull() {
  if (fetched) return
  fetched = true
  try {
    items.value = (await adminAnnouncementsApi.unread()).items
    if (items.value.length) show.value = true
  } catch {
    // 弹窗是增益：拉不到就安静跳过，不打断登录流程
  }
}
// spec §4.1：等 auth.ready（me 探测完成）再拉；挂载时已就绪则 immediate 立刻跑一次
watch(() => auth.ready, (v) => { if (v) pull() }, { immediate: true })

// 本弹窗是无用户手势自动弹出的（其他后台弹窗由点击触发，点击本身就把焦点带进弹窗）：
// Naive 的 trap-focus 会给背景容器加 aria-hidden，而焦点仍留在被隐藏的背景 <div> 里，
// Chrome 在打开这一刻就报 Blocked aria-hidden。故打开后赶在动画结束前把焦点移进弹窗。
// 优先「我知道了」按钮，取不到退回 Naive 关闭按钮 .n-base-close，再取不到则不处理。
async function focusIntoModal() {
  await nextTick()
  const close = document.querySelector<HTMLElement>('.n-modal .n-base-close')
  ;(confirmBtn.value ?? close ?? document.body).focus()
}
watch(show, (v) => { if (v) void focusIntoModal() })

async function onClose() {
  // 关闭时先把焦点移出弹窗：Naive 在 leave 阶段给弹窗容器加 aria-hidden，
  // 焦点若仍留在「我知道了」按钮上 Chrome 会报 Blocked aria-hidden 告警
  const el = document.activeElement
  if (el instanceof HTMLElement) el.blur()
  show.value = false
  // ids 快照必须在关闭这一刻取；reported 标记保证三条关闭路径只上报一次
  // （items 清空已推迟到动画结束，不能再只靠 items 是否为空来判重）
  if (reported) return
  const ids = items.value.map((i) => i.id)
  if (!ids.length) return
  reported = true
  try {
    await adminAnnouncementsApi.markRead(ids)
  } catch {
    message.warning('公告已读状态未能保存，下次登录可能再次看到')
  }
}

// items 清空推迟到淡出动画结束，避免关闭过程中弹窗变成「0 条未读」空壳
function onAfterLeave() {
  items.value = []
}
</script>

<template>
  <n-modal :show="show" preset="card" title="更新公告"
           :style="{ width: 'min(680px, calc(100vw - 48px))' }" :mask-closable="true"
           @update:show="(v: boolean) => { if (!v) onClose() }"
           @after-leave="onAfterLeave">
    <template #header-extra>
      <span class="text-xs text-ink-3">{{ items.length }} 条未读</span>
    </template>
    <div class="max-h-[60vh] space-y-4 overflow-y-auto pr-1">
      <article v-for="it in items" :key="it.id">
        <div class="flex flex-wrap items-baseline gap-2">
          <h3 class="font-bold">{{ it.title }}</h3>
          <span class="text-xs text-ink-3">{{ fmtDate(it.published_at ?? it.created_at) }}
            <template v-if="it.created_by"> · {{ it.created_by }}</template></span>
        </div>
        <div v-if="it.body_md" class="prose mt-1 text-sm" v-html="bodies.get(it.id)" />
      </article>
    </div>
    <template #footer>
      <div class="flex justify-end">
        <button ref="confirmBtn" class=" px-4 py-1.5 text-sm text-white" style="background: var(--c-primary)"
                @click="onClose">我知道了</button>
      </div>
    </template>
  </n-modal>
</template>
