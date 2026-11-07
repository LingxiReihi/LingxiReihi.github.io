<script setup lang="ts">
import { NButton, NDynamicInput, NInput, NSelect, NSpin, useMessage } from 'naive-ui'
import { computed, onMounted, reactive, ref } from 'vue'

import { adminAuthApi, adminProfileApi, siteApi } from '@/api'
import { ApiError } from '@/api/http'
import type { MediaAsset, MyProfile } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { useSiteStore } from '@/stores/site'
import MediaPicker from '@/components/admin/MediaPicker.vue'

const message = useMessage()
const auth = useAuthStore()
const siteStore = useSiteStore()
const loading = ref(true)
const savingKey = ref('')

const profile = reactive({
  nickname: '', signature: '', bio_md: '', avatar: '',
  social_links: [] as { platform: string; url: string }[],
  skills_text: '',   // 每行「组: a, b, c」
  experience: [] as { kind: string; title: string; org: string; start: string; end: string; desc: string }[],
})
const pickerOpen = ref(false)
const KIND_OPTIONS = [
  { label: '工作经历', value: 'work' },
  { label: '教育经历', value: 'edu' },
  { label: '项目经历', value: 'project' },
]

// ── 分板块编辑：默认只读，点「修改」才放开该板块的控件 ──
type SectionKey = 'basic' | 'social' | 'bio' | 'skills' | 'exp' | 'pwd'
const SECTION_FIELDS: Record<SectionKey, (keyof typeof profile)[]> = {
  basic: ['nickname', 'signature', 'avatar'],
  social: ['social_links'],
  bio: ['bio_md'],
  skills: ['skills_text'],
  exp: ['experience'],
  pwd: [],
}
const editing = reactive<Record<SectionKey, boolean>>({
  basic: false, social: false, bio: false, skills: false, exp: false, pwd: false,
})
const snapshot: Partial<Record<keyof typeof profile, unknown>> = {}
const openKey = computed(() => (Object.keys(editing) as SectionKey[]).find((k) => editing[k]) ?? '')

const clone = <T,>(v: T): T => (Array.isArray(v) ? JSON.parse(JSON.stringify(v)) : v)

function startEdit(k: SectionKey) {
  // 保存成功后整页会按服务端返回重填，同时开两块只会把另一块的未保存改动冲掉
  if (openKey.value && openKey.value !== k) {
    message.warning('请先保存或取消当前正在编辑的板块')
    return
  }
  for (const f of SECTION_FIELDS[k]) snapshot[f] = clone(profile[f])
  if (k === 'pwd') { pwd.old = ''; pwd.next = ''; pwd.confirm = '' }
  editing[k] = true
}

function cancel(k: SectionKey) {
  for (const f of SECTION_FIELDS[k]) (profile as any)[f] = clone(snapshot[f])
  editing[k] = false
}

function skillsToText(groups: { group: string; items: string[] }[]) {
  return (groups ?? []).map((g) => `${g.group}: ${(g.items ?? []).join(', ')}`).join('\n')
}
function textToSkills(text: string) {
  return text.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => {
    const [group, items] = l.split(/[:：](.*)/)
    return { group: (group ?? '').trim(), items: (items ?? '').split(/[,，]/).map((s) => s.trim()).filter(Boolean) }
  })
}
const skillGroups = computed(() => textToSkills(profile.skills_text))
const kindLabel = (kind: string) => KIND_OPTIONS.find((o) => o.value === kind)?.label ?? kind
const period = (e: { start: string; end: string }) =>
  `${e.start || '?'} – ${e.end || '至今'}`

function fill(p: MyProfile) {
  profile.nickname = p.nickname ?? ''
  profile.signature = p.signature ?? ''
  profile.bio_md = p.bio_md ?? ''
  profile.avatar = p.avatar ?? ''
  profile.social_links = p.social_links ?? []
  profile.skills_text = skillsToText(p.skills ?? [])
  profile.experience = (p.experience ?? []).map((e) => ({
    kind: e.kind ?? 'work', title: e.title ?? '', org: e.org ?? '', start: e.start ?? '', end: e.end ?? '', desc: e.desc ?? '',
  }))
}

async function load() {
  loading.value = true
  try {
    fill(await adminProfileApi.get())
  } catch (e: any) {
    message.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function saveFields(body: Parameters<typeof adminProfileApi.update>[0]) {
  try {
    fill(await adminProfileApi.update(body))
    // 资料会进首页/关于页与内容页署名：强制重取公开配置，避免前台仍显示旧昵称/头像
    await siteStore.reload(siteApi.config)
    return true
  } catch (e: any) {
    message.error(e?.message || '保存失败')
    return false
  }
}

const pwd = reactive({ old: '', next: '', confirm: '' })

async function saveSection(k: Exclude<SectionKey, 'pwd'>) {
  savingKey.value = k
  const body: Parameters<typeof adminProfileApi.update>[0] =
    k === 'basic' ? { nickname: profile.nickname, signature: profile.signature, avatar: profile.avatar }
      : k === 'social' ? { social_links: profile.social_links.filter((s) => s.url) }
      : k === 'bio' ? { bio_md: profile.bio_md }
      : k === 'skills' ? { skills: textToSkills(profile.skills_text) }
      : { experience: profile.experience.filter((e) => e.title) }
  const ok = await saveFields(body)
  if (ok) {
    editing[k] = false
    message.success('已保存，前台即时生效')
  }
  savingKey.value = ''
}

async function changePwd() {
  if (!pwd.old) { message.warning('请输入当前密码'); return }
  if (pwd.next.length < 8) { message.warning('新密码至少 8 位'); return }
  if (pwd.next !== pwd.confirm) { message.warning('两次输入的新密码不一致'); return }
  savingKey.value = 'pwd'
  try {
    await adminAuthApi.password(pwd.old, pwd.next)
    message.success('密码已更新，请重新登录')
    await auth.logout()
    location.href = '/admin/login'
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : '修改失败')
    savingKey.value = ''
  }
}

function onPickAvatar(a: MediaAsset) {
  profile.avatar = a.url   // 只改本地值，随「基本信息」板块一起保存
}
</script>

<template>
  <div>
    <h1 class="mb-1 text-2xl font-bold">我的资料</h1>
    <p class="mb-5 text-xs text-ink-3">每个板块默认只读，点右侧「修改」才编辑；取消即回滚，不会写库</p>
    <n-spin :show="loading">
      <div class="max-w-2xl space-y-4">

        <section class=" border border-line bg-surface p-5">
          <div class="mb-3 flex items-center justify-between">
            <h2 class="text-sm font-bold">基本信息</h2>
            <div class="flex gap-2">
              <template v-if="editing.basic">
                <n-button size="tiny" quaternary @click="cancel('basic')">取消</n-button>
                <n-button size="tiny" type="primary" :loading="savingKey === 'basic'" @click="saveSection('basic')">保存</n-button>
              </template>
              <n-button v-else size="tiny" @click="startEdit('basic')">修改</n-button>
            </div>
          </div>
          <template v-if="editing.basic">
            <div class="space-y-3">
              <div>
                <p class="mb-1 text-xs text-ink-3">昵称</p>
                <n-input v-model:value="profile.nickname" placeholder="展示在首页与内容署名的昵称" />
              </div>
              <div>
                <p class="mb-1 text-xs text-ink-3">一句话签名</p>
                <n-input v-model:value="profile.signature" />
              </div>
              <div>
                <p class="mb-1 text-xs text-ink-3">头像</p>
                <div class="flex items-center gap-3">
                  <img v-if="profile.avatar" :src="profile.avatar" class="h-14 w-14 rounded-full border border-line object-cover" alt="头像" />
                  <n-button size="small" @click="pickerOpen = true">{{ profile.avatar ? '更换头像' : '选择 / 上传素材' }}</n-button>
                  <n-button v-if="profile.avatar" size="small" quaternary @click="profile.avatar = ''">清除</n-button>
                </div>
              </div>
            </div>
          </template>
          <div v-else class="flex items-center gap-4">
            <img v-if="profile.avatar" :src="profile.avatar" class="h-14 w-14 rounded-full border border-line object-cover" alt="头像" />
            <div v-else class="flex h-14 w-14 items-center justify-center rounded-full border border-line bg-elevated text-xs text-ink-3">无头像</div>
            <div class="min-w-0">
              <p class="truncate font-medium">{{ profile.nickname || '—' }}</p>
              <p class="mt-1 truncate text-sm text-ink-3">{{ profile.signature || '未填签名' }}</p>
            </div>
          </div>
        </section>

        <section class=" border border-line bg-surface p-5">
          <div class="mb-3 flex items-center justify-between">
            <h2 class="text-sm font-bold">社交链接</h2>
            <div class="flex gap-2">
              <template v-if="editing.social">
                <n-button size="tiny" quaternary @click="cancel('social')">取消</n-button>
                <n-button size="tiny" type="primary" :loading="savingKey === 'social'" @click="saveSection('social')">保存</n-button>
              </template>
              <n-button v-else size="tiny" @click="startEdit('social')">修改</n-button>
            </div>
          </div>
          <n-dynamic-input
            v-if="editing.social"
            v-model:value="profile.social_links"
            :on-create="() => ({ platform: '', url: '' })"
          >
            <template #default="{ value }: any">
              <n-input v-model:value="value.platform" placeholder="GitHub" class="mr-2 !w-28" size="small" />
              <n-input v-model:value="value.url" placeholder="https://…" size="small" />
            </template>
          </n-dynamic-input>
          <ul v-else-if="profile.social_links.length" class="space-y-1 text-sm">
            <li v-for="(s, i) in profile.social_links" :key="i" class="truncate">
              <span class="text-ink-2">{{ s.platform || '链接' }}</span>
              <span class="ml-2 text-ink-3">{{ s.url }}</span>
            </li>
          </ul>
          <p v-else class="text-sm text-ink-3">暂无社交链接</p>
        </section>

        <section class=" border border-line bg-surface p-5">
          <div class="mb-3 flex items-center justify-between">
            <h2 class="text-sm font-bold">简介（Markdown）</h2>
            <div class="flex gap-2">
              <template v-if="editing.bio">
                <n-button size="tiny" quaternary @click="cancel('bio')">取消</n-button>
                <n-button size="tiny" type="primary" :loading="savingKey === 'bio'" @click="saveSection('bio')">保存</n-button>
              </template>
              <n-button v-else size="tiny" @click="startEdit('bio')">修改</n-button>
            </div>
          </div>
          <n-input
            v-if="editing.bio" v-model:value="profile.bio_md"
            type="textarea" :autosize="{ minRows: 4, maxRows: 12 }"
          />
          <p v-else-if="profile.bio_md" class="whitespace-pre-line text-sm leading-relaxed text-ink-2">{{ profile.bio_md }}</p>
          <p v-else class="text-sm text-ink-3">暂无简介</p>
        </section>

        <section class=" border border-line bg-surface p-5">
          <div class="mb-3 flex items-center justify-between">
            <h2 class="text-sm font-bold">技能栈</h2>
            <div class="flex gap-2">
              <template v-if="editing.skills">
                <n-button size="tiny" quaternary @click="cancel('skills')">取消</n-button>
                <n-button size="tiny" type="primary" :loading="savingKey === 'skills'" @click="saveSection('skills')">保存</n-button>
              </template>
              <n-button v-else size="tiny" @click="startEdit('skills')">修改</n-button>
            </div>
          </div>
          <template v-if="editing.skills">
            <p class="mb-1 text-xs text-ink-3">每行一组，格式：组名: 项1, 项2</p>
            <n-input v-model:value="profile.skills_text" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="前端: Vue 3, TypeScript" />
          </template>
          <ul v-else-if="skillGroups.length" class="space-y-1 text-sm">
            <li v-for="(g, i) in skillGroups" :key="i">
              <span class="text-ink-2">{{ g.group }}</span>
              <span class="mx-1 text-ink-3">·</span>
              <span class="text-ink-3">{{ g.items.join('、') }}</span>
            </li>
          </ul>
          <p v-else class="text-sm text-ink-3">暂无技能栈</p>
        </section>

        <section class=" border border-line bg-surface p-5">
          <div class="mb-3 flex items-center justify-between">
            <h2 class="text-sm font-bold">经历</h2>
            <div class="flex gap-2">
              <template v-if="editing.exp">
                <n-button size="tiny" quaternary @click="cancel('exp')">取消</n-button>
                <n-button size="tiny" type="primary" :loading="savingKey === 'exp'" @click="saveSection('exp')">保存</n-button>
              </template>
              <n-button v-else size="tiny" @click="startEdit('exp')">修改</n-button>
            </div>
          </div>
          <n-dynamic-input
            v-if="editing.exp"
            v-model:value="profile.experience"
            :on-create="() => ({ kind: 'work', title: '', org: '', start: '', end: '', desc: '' })"
          >
            <template #default="{ value }: any">
              <div class="grid w-full grid-cols-2 gap-2">
                <n-select v-model:value="value.kind" :options="KIND_OPTIONS" size="small" />
                <n-input v-model:value="value.title" placeholder="标题（如 软件工程师）" size="small" />
                <n-input v-model:value="value.org" placeholder="单位 / 学校" size="small" />
                <div class="flex gap-2">
                  <n-input v-model:value="value.start" placeholder="2022-07" size="small" />
                  <n-input v-model:value="value.end" placeholder="留空 = 至今" size="small" />
                </div>
                <n-input v-model:value="value.desc" placeholder="一句话说明（可留空）" size="small" class="col-span-2" />
              </div>
            </template>
          </n-dynamic-input>
          <ul v-else-if="profile.experience.length" class="space-y-2 text-sm">
            <li v-for="(e, i) in profile.experience.filter((x) => x.title)" :key="i">
              <div class="flex flex-wrap items-baseline gap-x-2">
                <span class="bg-elevated px-1.5 py-0.5 text-xs text-ink-3">{{ kindLabel(e.kind) }}</span>
                <span class="font-medium">{{ e.title }}</span>
                <span v-if="e.org" class="text-ink-3">{{ e.org }}</span>
                <span class="ml-auto text-xs text-ink-3">{{ period(e) }}</span>
              </div>
              <p v-if="e.desc" class="mt-1 text-xs text-ink-3">{{ e.desc }}</p>
            </li>
          </ul>
          <p v-else class="text-sm text-ink-3">暂无经历</p>
        </section>

        <section class=" border border-line bg-surface p-5">
          <div class="mb-3 flex items-center justify-between">
            <h2 class="text-sm font-bold">密码设置</h2>
            <div class="flex gap-2">
              <template v-if="editing.pwd">
                <n-button size="tiny" quaternary @click="cancel('pwd')">取消</n-button>
                <n-button size="tiny" type="primary" :loading="savingKey === 'pwd'" @click="changePwd">修改密码</n-button>
              </template>
              <n-button v-else size="tiny" @click="startEdit('pwd')">修改</n-button>
            </div>
          </div>
          <div v-if="editing.pwd" class="space-y-3">
            <div>
              <p class="mb-1 text-xs text-ink-3">当前密码</p>
              <n-input v-model:value="pwd.old" type="password" show-password-on="click" autocomplete="current-password" />
            </div>
            <div>
              <p class="mb-1 text-xs text-ink-3">新密码（≥8 位）</p>
              <n-input v-model:value="pwd.next" type="password" show-password-on="click" autocomplete="new-password" />
            </div>
            <div>
              <p class="mb-1 text-xs text-ink-3">确认新密码</p>
              <n-input v-model:value="pwd.confirm" type="password" show-password-on="click" autocomplete="new-password" />
            </div>
            <p class="text-xs text-ink-3">保存成功后该账号在所有设备上的登录态都会失效，需用新密码重新登录。</p>
          </div>
          <p v-else class="text-sm text-ink-3">
            密码在此页修改（需先输当前密码）。改成功后所有设备都要重新登录；忘了密码可在登录页点「忘记密码」，随机新口令会发到你绑定的邮箱。
          </p>
        </section>

      </div>
    </n-spin>

    <MediaPicker :show="pickerOpen" kind="image" category="avatar" select-on-upload @update:show="pickerOpen = $event" @select="onPickAvatar" />
  </div>
</template>
