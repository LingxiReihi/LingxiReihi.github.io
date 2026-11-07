<script setup lang="ts">
import type { CommentOut } from '@/api/types'
import { onMounted, ref } from 'vue'

import { commentsApi } from '@/api'
import { formatDate } from '@/utils/format'

const props = defineProps<{ contentId: number }>()

const readLS = (k: string) => (typeof localStorage === 'undefined' ? '' : localStorage.getItem(k) || '')

const items = ref<CommentOut[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)

const nickname = ref(readLS('comment_nickname'))
const email = ref(readLS('comment_email'))
const body = ref('')
const website = ref('')   // 蜜罐：真人不可见不填
const submitting = ref(false)
const notice = ref('')
const errMsg = ref('')

async function load(reset = false) {
  if (loading.value) return
  loading.value = true
  try {
    if (reset) { page.value = 1; items.value = [] }
    const d = await commentsApi.list(props.contentId, page.value, pageSize)
    items.value = reset ? d.items : [...items.value, ...d.items]
    total.value = d.total
  } catch { /* 评论区非关键，静默 */ } finally {
    loading.value = false
  }
}
onMounted(() => load(true))

function loadMore() {
  page.value += 1
  load()
}

async function submit() {
  if (submitting.value) return
  submitting.value = true
  errMsg.value = ''
  try {
    await commentsApi.create({
      content_id: props.contentId, nickname: nickname.value.trim(),
      email: email.value.trim(), body: body.value.trim(), website: website.value,
    })
    localStorage.setItem('comment_nickname', nickname.value.trim())
    localStorage.setItem('comment_email', email.value.trim())
    body.value = ''
    notice.value = '评论已提交，通过审核后展示，感谢参与！'
  } catch (e: any) {
    errMsg.value = e?.message || '提交失败，请稍后再试'
  } finally {
    submitting.value = false
  }
}

const canSubmit = () =>
  nickname.value.trim() && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.value.trim()) && body.value.trim()
</script>

<template>
  <section class="mt-12 border-t border-line pt-8">
    <h2 class="text-lg font-bold">评论 <span v-if="total" class="text-sm font-normal text-ink-3">({{ total }})</span></h2>

    <div class="mt-5 rounded-xl border border-line bg-surface p-4">
      <p class="mb-3 text-xs text-ink-3">评论经作者审核通过后展示；邮箱不会公开显示（头像按邮箱从开源图包里固定取一张，同一邮箱同一张；管理员账号显示其个人头像）。</p>
      <div class="grid gap-3 sm:grid-cols-2">
        <input v-model="nickname" maxlength="50" placeholder="昵称 *"
               class="rounded-lg border border-line bg-transparent px-3 py-2 text-sm outline-none focus:border-brand" >
        <input v-model="email" type="email" maxlength="120" placeholder="邮箱 *"
               class="rounded-lg border border-line bg-transparent px-3 py-2 text-sm outline-none focus:border-brand" >
      </div>
      <!-- 蜜罐字段：对真人隐藏 -->
      <input v-model="website" type="text" name="website" tabindex="-1" autocomplete="off"
             class="absolute h-0 w-0 opacity-0" aria-hidden="true" style="position:absolute;left:-9999px" >
      <textarea v-model="body" maxlength="500" rows="3" placeholder="友善发言，1–500 字 *"
                class="mt-3 w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm outline-none focus:border-brand" />
      <div class="mt-2 flex flex-wrap items-center gap-3">
        <button
          class="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-black transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="submitting || !canSubmit()" @click="submit"
        >{{ submitting ? '提交中…' : '提交评论' }}</button>
        <span v-if="errMsg" class="text-xs text-red-400">{{ errMsg }}</span>
      </div>
      <p v-if="notice" class="mt-2 rounded-lg border border-brand/30 bg-brand/10 px-3 py-2 text-xs text-brand">{{ notice }}</p>
    </div>

    <ul v-if="items.length" class="mt-6 space-y-5">
      <li v-for="c in items" :key="c.id" class="flex gap-3">
        <img :src="c.avatar" :alt="c.nickname" loading="lazy" class="h-9 w-9 shrink-0 rounded-full border border-line" />
        <div class="min-w-0 flex-1">
          <p class="text-sm">
            <span class="font-medium">{{ c.nickname }}</span>
            <time class="ml-2 text-xs text-ink-3">{{ formatDate(c.created_at) }}</time>
          </p>
          <p class="mt-1 whitespace-pre-wrap break-words text-sm text-ink-2">{{ c.body }}</p>
        </div>
      </li>
    </ul>
    <p v-else-if="!loading" class="mt-6 text-sm text-ink-3">还没有评论，来抢沙发吧。</p>
    <button v-if="items.length < total" class="mt-4 text-sm text-brand hover:underline" :disabled="loading" @click="loadMore">
      加载更多评论（{{ items.length }}/{{ total }}）
    </button>
  </section>
</template>
