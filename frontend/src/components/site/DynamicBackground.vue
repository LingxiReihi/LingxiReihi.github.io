<script setup lang="ts">
/**
 * 前台动态背景：扫描线（仪器面板基调）。
 * 三层叠加，全部走 CSS，不再用 canvas 粒子：
 *  1) CRT 细扫描线：3px 一行的极淡横线
 *  2) 缓慢下移的扫描带：一条 12% 高的柔光，18s 循环
 *  3) 顶部主色微光 + 四角暗角
 * 固定层 z-0、pointer-events-none；prefers-reduced-motion 时停掉扫描带。
 */
</script>

<template>
  <div class="site-bg" aria-hidden="true">
    <div class="site-bg__lines" />
    <div class="site-bg__sweep" />
    <div class="site-bg__glow" />
  </div>
</template>

<style scoped>
.site-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}

/* 细扫描线：3px 一行，亮度随主题走 */
.site-bg__lines {
  position: absolute;
  inset: 0;
  background-image: repeating-linear-gradient(
    to bottom,
    color-mix(in srgb, var(--c-text) 4%, transparent) 0px,
    color-mix(in srgb, var(--c-text) 4%, transparent) 1px,
    transparent 1px,
    transparent 3px
  );
  opacity: 0.55;
}

/* 扫描带：一条柔光从上往下扫 */
.site-bg__sweep {
  position: absolute;
  left: 0;
  right: 0;
  height: 18vh;
  background: linear-gradient(
    to bottom,
    transparent,
    color-mix(in srgb, var(--c-primary) 7%, transparent) 45%,
    color-mix(in srgb, var(--c-primary) 11%, transparent) 50%,
    color-mix(in srgb, var(--c-primary) 7%, transparent) 55%,
    transparent
  );
  animation: site-sweep 18s linear infinite;
  will-change: transform;
}

@keyframes site-sweep {
  0% { transform: translate3d(0, -20vh, 0); }
  100% { transform: translate3d(0, 100vh, 0); }
}

/* 顶部主色微光 + 底部压暗，让内容区更聚焦 */
.site-bg__glow {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(120% 60% at 50% -10%, color-mix(in srgb, var(--c-primary) 10%, transparent), transparent 62%),
    radial-gradient(100% 55% at 50% 108%, color-mix(in srgb, var(--c-bg) 70%, transparent), transparent 60%);
}

@media (prefers-reduced-motion: reduce) {
  .site-bg__sweep {
    animation: none;
    opacity: 0;
  }
}
</style>
