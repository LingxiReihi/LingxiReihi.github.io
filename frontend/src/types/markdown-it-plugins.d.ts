// markdown-it-sub / -sup / -mark 只发了 JS、没带 .d.ts（实测 v2.0.0 / v4.0.0），签名就是插件函数。
// 必须单独成文件且顶层不能有 import/export：一旦文件是模块，declare module 就被解析成
// 「模块增强」，对本来没有类型的包整体失效，TS7016 照旧报（写进带 export{} 的 shims.d.ts 踩过）。
declare module 'markdown-it-sub' {
  import type MarkdownIt from 'markdown-it'
  const plugin: (md: InstanceType<typeof MarkdownIt>) => void
  export default plugin
}

declare module 'markdown-it-sup' {
  import type MarkdownIt from 'markdown-it'
  const plugin: (md: InstanceType<typeof MarkdownIt>) => void
  export default plugin
}

declare module 'markdown-it-mark' {
  import type MarkdownIt from 'markdown-it'
  const plugin: (md: InstanceType<typeof MarkdownIt>) => void
  export default plugin
}
