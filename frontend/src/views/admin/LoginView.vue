<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NAlert, NButton, NCheckbox, NConfigProvider, NForm, NFormItem, NInput, NModal,
} from 'naive-ui'

import { adminAuthApi } from '@/api'
import { ApiError } from '@/api/http'
import { useAdminTheme } from '@/composables/useAdminTheme'
import { useAuthStore } from '@/stores/auth'

const { naiveTheme, themeOverrides } = useAdminTheme()

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const username = ref('')
const password = ref('')
const remember = ref(true)
const submitting = ref(false)
const formError = ref('')
const lockCountdown = ref(0)
let lockTimer: number | undefined

async function submit() {
  if (!username.value || !password.value) {
    formError.value = '请输入账号和密码'
    return
  }
  submitting.value = true
  formError.value = ''
  try {
    await auth.login(username.value, password.value, remember.value)
    router.replace(String(route.query.redirect || '/admin/dashboard'))
  } catch (e) {
    if (e instanceof ApiError) {
      if (e.code === 42300) {
        lockCountdown.value = Number((e.data as any)?.retry_after ?? 60)
        clearInterval(lockTimer)
        lockTimer = window.setInterval(() => {
          lockCountdown.value -= 1
          if (lockCountdown.value <= 0) clearInterval(lockTimer)
        }, 1000)
      } else {
        formError.value = e.message
      }
    } else formError.value = '网络错误，请稍后再试'
  } finally {
    submitting.value = false
  }
}

const forgotOpen = ref(false)
const forgotName = ref('')
const forgotBusy = ref(false)
const forgotError = ref('')
const forgotHint = ref('')

function openForgot() {
  forgotName.value = username.value
  forgotError.value = ''
  forgotHint.value = ''
  forgotOpen.value = true
}

async function sendForgot() {
  const name = forgotName.value.trim()
  if (!name) {
    forgotError.value = '请输入管理员账号名'
    return
  }
  forgotBusy.value = true
  forgotError.value = ''
  try {
    // 「账号不存在 / 没填邮箱 / 被冷却挡下」服务端一律给同一句话，界面不得各自改写措辞
    forgotHint.value = await adminAuthApi.forgotPassword(name)
  } catch (e) {
    forgotError.value = e instanceof ApiError ? e.message : '网络错误，请稍后再试'
  } finally {
    forgotBusy.value = false
  }
}
</script>

<template>
  <n-config-provider :theme="naiveTheme" :theme-overrides="themeOverrides">
    <div class="hud-grid flex min-h-screen items-center justify-center bg-bg px-4">
    <div class="w-full max-w-sm">
      <div class="mb-8 text-center">
        <RouterLink to="/" class="font-mono text-xl font-semibold tracking-[0.2em] text-brand">PERSONAL-WEB</RouterLink>
        <p class="mt-2 font-mono text-[10px] uppercase tracking-[0.24em] text-ink-3">Admin Console</p>
      </div>
      <div class="relative border border-line bg-surface p-6">
        <span class="pointer-events-none absolute left-0 top-0 h-2.5 w-2.5 border-l border-t border-brand" aria-hidden="true" />
        <span class="pointer-events-none absolute bottom-0 right-0 h-2.5 w-2.5 border-b border-r border-brand" aria-hidden="true" />
        <n-form @submit.prevent="submit">
          <n-form-item label="账号">
            <n-input v-model:value="username" placeholder="admin" autocomplete="username" :disabled="lockCountdown > 0" />
          </n-form-item>
          <n-form-item label="密码">
            <n-input
              v-model:value="password" type="password" show-password-on="click"
              placeholder="••••••••" autocomplete="current-password"
              :disabled="lockCountdown > 0" @keyup.enter="submit"
            />
          </n-form-item>
          <div class="mb-4 flex items-center justify-between">
            <n-checkbox v-model:checked="remember" class="text-sm">记住登录（7 天免登录）</n-checkbox>
            <button type="button" class="text-xs text-ink-3 transition-colors hover:text-brand" @click="openForgot">
              忘记密码？
            </button>
          </div>
          <n-alert v-if="formError" type="error" class="mb-4" :show-icon="true">{{ formError }}</n-alert>
          <n-alert v-if="lockCountdown > 0" type="warning" class="mb-4" :show-icon="true">
            失败次数过多，账号已锁定 {{ lockCountdown }} 秒
          </n-alert>
          <n-button type="primary" block :loading="submitting" :disabled="lockCountdown > 0" @click="submit">
            登 录
          </n-button>
        </n-form>
      </div>
      <p class="mt-6 text-center text-xs text-ink-3">
        <RouterLink to="/" class="hover:text-brand">← 返回前台</RouterLink>
      </p>

      <n-modal
        :show="forgotOpen" preset="card" title="忘记密码"
        style="width: 420px; max-width: 94vw; border-radius: 16px"
        @update:show="(v: boolean) => { forgotOpen = v }"
      >
        <p class="text-sm text-ink-2">
          输入管理员账号名，系统会生成随机新口令并发送到该账号绑定的邮箱；旧会话同时下线。
        </p>
        <n-input
          v-model:value="forgotName" placeholder="admin" class="mt-3"
          :disabled="forgotBusy" @keyup.enter="sendForgot"
        />
        <n-alert v-if="forgotError" type="error" class="mt-3" :show-icon="true">{{ forgotError }}</n-alert>
        <n-alert v-if="forgotHint" type="success" class="mt-3" :show-icon="true">{{ forgotHint }}</n-alert>
        <div class="mt-4 flex justify-end gap-2">
          <n-button size="small" @click="forgotOpen = false">关闭</n-button>
          <n-button size="small" type="primary" :loading="forgotBusy" @click="sendForgot">发送重置邮件</n-button>
        </div>
      </n-modal>
      </div>
    </div>
  </n-config-provider>
</template>
