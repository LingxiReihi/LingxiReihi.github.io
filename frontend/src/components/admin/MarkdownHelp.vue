<script setup lang="ts">
import { MD_HTML_TAGS } from '@/composables/useMd'

const MD_BASICS: { eg: string; desc: string }[] = [
  { eg: '# 一级标题 … ###### 六级', desc: '标题（二级、三级会进目录）' },
  { eg: '**加粗**  *斜体*  ~~删除线~~', desc: '强调' },
  { eg: '[链接文字](https://example.com)', desc: '链接（自动识别裸网址）' },
  { eg: '![图注](/media/2026/09/x.png)', desc: '图片' },
  { eg: '- 无序项    1. 有序项    - [ ] 待办', desc: '列表与任务列表' },
  { eg: '> 引用的一段话', desc: '引用块' },
  { eg: '`行内代码`', desc: '行内代码' },
  { eg: '```python\\nprint(1)\\n```', desc: '代码块（带语言名，右上角出语言标签）' },
  { eg: '| 甲 | 乙 |\\n| --- | --- |\\n| 1 | 2 |', desc: '表格' },
  { eg: '---', desc: '分隔线' },
]

const SITE_ONLY: { eg: string; desc: string }[] = [
  { eg: '@[TOC]  或  @[TOC](文章目录)', desc: '在此处内嵌目录（标题进视口才算，二级三级入表）' },
  { eg: '<img src="…" style="zoom: 67%;" />', desc: 'Typora 导出的缩放图，按百分比控宽' },
]

const EXTENSIONS: { eg: string; desc: string }[] = [
  { eg: '~~弃用~~', desc: '删除线' },
  { eg: 'H~2~O', desc: '下标（内侧不能有空格，否则按字面显示）' },
  { eg: 'X^2^', desc: '上标' },
  { eg: '==重点==', desc: '高亮底色' },
  { eg: '$E=mc^2$', desc: '行内公式（KaTeX，构建期就渲染进 HTML）' },
]

const entries = Object.entries(MD_HTML_TAGS)
const inlineTags = entries.filter(([, s]) => !s.block)
const blockTags = entries.filter(([, s]) => s.block)

const REJECTED = [
  '<script> <style> <link> <meta> <form> <input> <iframe>（嵌入一律不支持）',
  'class 属性：站点没有配套类名，写了不生效，样式请走行内 style',
  '任何 on* 事件属性（onerror / onclick …）',
  'href/src 里的 javascript:、data:、vbscript: 协议',
  'style 里的 position、url()、expression、behavior（防覆盖整站界面）',
]

defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()
</script>

<template>
  <Transition name="md-help">
    <aside
      v-show="show"
      class="absolute inset-y-0 right-0 z-20 flex w-[380px] max-w-[92%] flex-col  border border-line bg-surface shadow-2xl"
      aria-label="Markdown 与 HTML 语法提示"
    >
      <div class="flex shrink-0 items-center gap-2 border-b border-line px-4 py-2.5">
        <p class="text-sm font-medium text-ink">语法提示</p>
        <button
          class="ml-auto px-2 py-1 text-xs text-ink-3 hover:bg-elevated hover:text-ink"
          aria-label="向右收起语法提示"
          @click="emit('close')"
        >收起 →</button>
      </div>

      <div class="min-h-0 flex-1 space-y-5 overflow-auto px-4 py-3 text-xs leading-relaxed">
        <section>
          <p class="mb-1.5 font-medium text-ink-2">Markdown 基础</p>
          <dl class="space-y-1.5">
            <div v-for="m in MD_BASICS" :key="m.eg" class="grid grid-cols-[1fr_auto] items-start gap-x-3">
              <code class="col-span-2 break-all bg-elevated px-1.5 py-1 font-mono text-[11px] text-brand">{{ m.eg }}</code>
              <dd class="col-span-2 -mt-1 text-ink-3">{{ m.desc }}</dd>
            </div>
          </dl>
        </section>

        <section>
          <p class="mb-1.5 font-medium text-ink-2">扩展语法</p>
          <dl class="space-y-1.5">
            <div v-for="m in EXTENSIONS" :key="m.eg">
              <code class="block break-all bg-elevated px-1.5 py-1 font-mono text-[11px] text-brand">{{ m.eg }}</code>
              <dd class="mt-0.5 text-ink-3">{{ m.desc }}</dd>
            </div>
          </dl>
          <p class="mt-2 text-ink-3">
            公式里的 <code class="text-brand">$</code> 若与正文里的美元金额撞上了，把金额写成
            <code class="text-brand">\$5</code> 或放进行内代码 <code class="text-brand">`$5`</code> 即可；
            代码块与行内代码里的这些符号一律按原样显示。
          </p>
        </section>

        <section>
          <p class="mb-1.5 font-medium text-ink-2">本站特有</p>
          <dl class="space-y-1.5">
            <div v-for="m in SITE_ONLY" :key="m.eg">
              <code class="block break-all bg-elevated px-1.5 py-1 font-mono text-[11px] text-brand">{{ m.eg }}</code>
              <dd class="mt-0.5 text-ink-3">{{ m.desc }}</dd>
            </div>
          </dl>
        </section>

        <section>
          <p class="mb-1.5 font-medium text-ink-2">支持的 HTML 标签 · 行内</p>
          <p class="mb-2 text-ink-3">写在句子中间即可生效；属性只认下面列出的，其余会被丢掉。</p>
          <ul class="space-y-1.5">
            <li v-for="[name, s] in inlineTags" :key="name">
              <code class="break-all bg-elevated px-1.5 py-1 font-mono text-[11px] text-brand">{{ s.eg }}</code>
              <span class="mt-0.5 block text-ink-3">
                &lt;{{ name }}&gt; {{ s.desc }}
                <template v-if="s.attrs?.length"> · 属性 {{ s.attrs.join(' / ') }}</template>
                <template v-if="s.style !== false"> · 可用 style</template>
              </span>
            </li>
          </ul>
        </section>

        <section>
          <p class="mb-1.5 font-medium text-ink-2">支持的 HTML 标签 · 块级</p>
          <p class="mb-2 text-ink-3">请<strong class="text-ink">独占一行</strong>书写，与上下文之间留空行，否则会被当成普通段落文字。</p>
          <ul class="space-y-1.5">
            <li v-for="[name, s] in blockTags" :key="name">
              <code class="break-all bg-elevated px-1.5 py-1 font-mono text-[11px] text-brand">{{ s.eg }}</code>
              <span class="mt-0.5 block text-ink-3">
                &lt;{{ name }}&gt; {{ s.desc }}
                <template v-if="s.attrs?.length"> · 属性 {{ s.attrs.join(' / ') }}</template>
                <template v-if="s.style !== false"> · 可用 style</template>
              </span>
            </li>
          </ul>
        </section>

        <section>
          <p class="mb-1.5 font-medium text-ink-2">可以用的 style 属性</p>
          <p class="break-words font-mono text-[11px] text-ink-3">
            color · background-color · font-size · font-weight · font-style · font-family · text-align ·
            text-decoration · text-indent · line-height · letter-spacing · margin* · padding* · width ·
            max-width · min-width · border · border-radius · display · white-space · vertical-align
          </p>
        </section>

        <section>
          <p class="mb-1.5 font-medium text-warning">一律不放行（会按字面显示成文本）</p>
          <ul class="list-disc space-y-1 pl-4 text-ink-3">
            <li v-for="r in REJECTED" :key="r">{{ r }}</li>
          </ul>
        </section>

        <p class="border-t border-line pt-3 text-ink-3">
          代码块与行内代码里的尖括号不受影响，教程示例照原样显示。
        </p>
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
/* 从右边缘滑入滑出；收起后 v-show 置 display:none，不会撑出横向滚动条 */
.md-help-enter-active,
.md-help-leave-active {
  transition: transform 0.22s ease, opacity 0.22s ease;
}
.md-help-enter-from,
.md-help-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .md-help-enter-active,
  .md-help-leave-active {
    transition: none;
  }
}
</style>
