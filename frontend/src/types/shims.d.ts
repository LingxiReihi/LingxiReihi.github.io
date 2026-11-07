export {}

declare module 'vue' {
  interface GlobalComponents {
    'model-viewer': import('vue').DefineComponent<Record<string, any>, Record<string, any>>
  }
}
