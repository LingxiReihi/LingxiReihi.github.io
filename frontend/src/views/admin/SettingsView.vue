<script setup lang="ts">
import {
  NButton, NDynamicInput, NForm, NFormItem, NInput, NSwitch, NTabPane, NTabs,
  useMessage,
} from 'naive-ui'
import { onMounted, reactive, ref } from 'vue'

import { adminSettingsApi, siteApi } from '@/api'
import MediaPicker from '@/components/admin/MediaPicker.vue'
import { useSiteStore } from '@/stores/site'
import type { MediaAsset } from '@/api/types'

const message = useMessage()
const siteStore = useSiteStore()
const loading = ref(true)
const savingGroup = ref('')
const iconPicker = ref(false)

const site = reactive({ title: '', subtitle: '', description: '', favicon: '', icon: '' })
const nav = reactive({ items: [] as { label: string; path: string; visible: boolean; order: number }[] })
const footer = reactive({ copyright: '', beian: '', links: [] as { platform: string; url: string }[] })
const mail = reactive({ apiUrl: '', apiKey: '', overrideTo: '', keySet: false, keyHint: '' })

async function load() {
  loading.value = true
  try {
    const all = await adminSettingsApi.getAll()
    Object.assign(site, { title: '', subtitle: '', description: '', favicon: '', icon: '', ...(all.site ?? {}) })
    nav.items = (((all.nav?.items as any[]) ?? []) as any[]).map((i, idx) => ({ visible: true, order: idx + 1, ...i }))
    const f = all.footer ?? {}
    footer.copyright = String(f.copyright ?? '')
    footer.beian = String(f.beian ?? '')
    footer.links = (f.links as any[]) ?? []
    const m = all.mail ?? {}
    mail.apiUrl = String(m.api_url ?? '')
    mail.overrideTo = String(m.override_to ?? '')
    mail.keySet = Boolean(m.api_key_set)
    mail.keyHint = String(m.api_key_hint ?? '')
    mail.apiKey = ''      // 接口只回掩码，输入框每次从空开始
  } catch (e: any) {
    message.error(e?.message || '设置加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function save(group: 'site' | 'nav' | 'footer' | 'mail') {
  savingGroup.value = group
  try {
    let body: Record<string, unknown>
    if (group === 'site') body = { ...site }
    else if (group === 'nav') {
      body = { items: nav.items.map((i, idx) => ({ ...i, order: i.order ?? idx + 1 })) }
    } else if (group === 'mail') {
      body = { api_url: mail.apiUrl, api_key: mail.apiKey, override_to: mail.overrideTo }
    } else body = { copyright: footer.copyright, beian: footer.beian, links: footer.links.filter((l) => l.url) }
    const data = await adminSettingsApi.putGroup(group, body)
    if (group === 'mail') {
      // 后端只回掩码：保存成功后按响应刷新「已配置/尾号」，输入框清空等下次改
      const m = (data.mail ?? data) as Record<string, unknown>
      mail.keySet = Boolean(m.api_key_set)
      mail.keyHint = String(m.api_key_hint ?? '')
      mail.apiKey = ''
      message.success('邮件通道已保存')
      return
    }
    // 同标签页前台共享 site store：强制重取，避免返回前台仍显示旧配置
    await siteStore.reload(siteApi.config)
    message.success('已保存，前台即时生效')
  } catch (e: any) {
    message.error(e?.message || '保存失败')
  } finally {
    savingGroup.value = ''
  }
}
function onPickIcon(a: MediaAsset) {
  site.icon = a.url   // 只改本地值，随「保存站点信息」一起写入
}
</script>

<template>
  <div>
    <h1 class="mb-5 text-2xl font-bold">站点设置</h1>
    <n-tabs type="line" animated>
      <n-tab-pane name="site" tab="站点信息">
        <n-form label-placement="top" class="max-w-xl">
          <n-form-item label="站点名（顶栏、首页大标题、各页标题后缀）"><n-input v-model:value="site.title" /></n-form-item>
          <n-form-item label="副标题（首页眉题；留空则该行不显示）"><n-input v-model:value="site.subtitle" /></n-form-item>
          <n-form-item label="站点描述（首页介绍正文 + 各页 SEO 描述）">
            <n-input v-model:value="site.description" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
          </n-form-item>
          <n-form-item label="网站图标（首页首屏右侧的圆形大图；留空则该图不显示）">
            <div class="flex items-center gap-3">
              <img v-if="site.icon" :src="site.icon" class="h-14 w-14 rounded-full border border-line object-cover" alt="网站图标预览" />
              <n-button size="small" @click="iconPicker = true">{{ site.icon ? '更换图片' : '选择 / 上传素材' }}</n-button>
              <n-button v-if="site.icon" size="small" quaternary @click="site.icon = ''">清除</n-button>
            </div>
          </n-form-item>
          <n-form-item label="Favicon URL（浏览器标签页小图标；留空用内置 /favicon.svg）"><n-input v-model:value="site.favicon" placeholder="/media/… 或留空" /></n-form-item>
          <n-button type="primary" :loading="savingGroup === 'site'" @click="save('site')">保存站点信息</n-button>
        </n-form>
      </n-tab-pane>

      <n-tab-pane name="nav" tab="导航与页脚">
        <div class="max-w-3xl">
          <p class="mb-2 text-sm text-ink-2">导航项（顺序即显示顺序）</p>
          <!-- 带自定义 #default 模板时必须给 on-create：naive-ui 2.45 的 createItem 在
               「有 slot 但没有 onCreate」时插入的是 null，模板里 value.label 当场渲染报错 = 点了 Create 没反应。
               :default-value 只在非受控用法下当初始值，配 v-model 完全不参与，别拿它当新建模板。 -->
          <n-dynamic-input v-model:value="nav.items" :on-create="() => ({ label: '', path: '/', visible: true, order: nav.items.length + 1 })">
            <template #default="{ value }: any">
              <div class="grid w-full grid-cols-[1fr_1fr_auto] items-center gap-2">
                <n-input v-model:value="value.label" placeholder="标签" size="small" />
                <n-input v-model:value="value.path" placeholder="/blog" size="small" />
                <label class="flex items-center gap-1 text-xs text-ink-3"><n-switch v-model:value="value.visible" size="small" />显示</label>
              </div>
            </template>
          </n-dynamic-input>
          <n-button size="small" class="mt-2" @click="save('nav')" :loading="savingGroup === 'nav'">保存导航</n-button>

          <div class="mt-8 space-y-3">
            <p class="text-sm text-ink-2">页脚文字</p>
            <p class="text-xs text-ink-3">页脚当前固定显示「© 年份 站点名 · RSS · Sitemap」，下面两项只入库，暂不渲染。</p>
            <n-input v-model:value="footer.copyright" placeholder="版权行，如 © 2026 Yimu" />
            <n-input v-model:value="footer.beian" placeholder="备案号（海外服务器可留空）" />
            <p class="pt-2 text-sm text-ink-2">友站链接（显示在首页首屏按钮下方）</p>
            <n-dynamic-input v-model:value="footer.links" :on-create="() => ({ platform: '', url: '' })">
              <template #default="{ value }: any">
                <div class="grid w-full grid-cols-2 gap-2">
                  <n-input v-model:value="value.platform" placeholder="站点名（留空则用对方域名）" size="small" />
                  <n-input v-model:value="value.url" placeholder="https://…（必须写完整地址）" size="small" />
                </div>
              </template>
            </n-dynamic-input>
            <n-button size="small" type="primary" :loading="savingGroup === 'footer'" @click="save('footer')">保存页脚</n-button>
          </div>
        </div>
      </n-tab-pane>

      <n-tab-pane name="mail" tab="邮件通道">
        <n-form label-placement="top" class="max-w-xl">
          <n-form-item label="发信接口地址">
            <n-input v-model:value="mail.apiUrl" placeholder="http://mail:8000/api/external/send" />
          </n-form-item>
          <n-form-item label="API Key（只写入、不回显）">
            <n-input
              v-model:value="mail.apiKey" type="password" show-password-on="click"
              :placeholder="mail.keySet ? `已配置（尾号 ${mail.keyHint}），留空则不修改` : '在 mail 站设置页「外部接入 API」生成后粘贴到这里'"
            />
          </n-form-item>
          <n-form-item label="测试收件人（留空 = 各管理员发到各自绑定邮箱）">
            <n-input v-model:value="mail.overrideTo" placeholder="orihiya@foxmail.com" />
          </n-form-item>
          <n-button type="primary" :loading="savingGroup === 'mail'" @click="save('mail')">保存邮件通道</n-button>
          <p class="mt-3 text-xs leading-relaxed text-ink-3">
            Key 在库里以密文保存，主密钥由 JWT_SECRET 派生：改了 JWT_SECRET 就要重填一次。
            填好后登录页的「忘记密码」才会把随机新口令发到管理员邮箱；这里留空则自助重置不可用。
            测试收件人非空时所有重置邮件都改投该地址，只应在排障时临时打开。
          </p>
        </n-form>
      </n-tab-pane>

    </n-tabs>

    <MediaPicker :show="iconPicker" kind="image" category="site" select-on-upload
                 @update:show="iconPicker = $event" @select="onPickIcon" />
  </div>
</template>
