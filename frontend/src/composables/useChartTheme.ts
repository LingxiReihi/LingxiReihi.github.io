import { computed } from 'vue'

import { useThemeStore } from '@/stores/theme'

const MONO = "ui-monospace, 'JetBrains Mono', Consolas, monospace"

/**
 * 后台图表的统一视觉（HUD 基调）：等宽刻度、虚线分隔、直角柱、细线无拐点。
 * 颜色从主题模式推出来，切换亮暗时图表会跟着重绘 —— 之前是写死的深色值，亮色下直接看不清。
 */
export function useChartTheme() {
  const theme = useThemeStore()
  const dark = computed(() => theme.mode === 'dark')

  const c = computed(() =>
    dark.value
      ? { panel: '#0f1826', border: '#1f2c47', text: '#e6edf3', text2: '#9fb0c3', text3: '#5f7185', primary: '#39c5bb', primary2: '#5ee0d6' }
      : { panel: '#ffffff', border: '#e2e8f0', text: '#0f172a', text2: '#475569', text3: '#94a3b8', primary: '#0d9488', primary2: '#14b8a6' },
  )

  /** 系列配色：主色 → 亮主色 → 中性灰蓝 */
  const palette = computed(() => [c.value.primary, c.value.primary2, c.value.text2])

  const axisLabel = computed(() => ({ color: c.value.text3, fontFamily: MONO, fontSize: 10 }))
  const axisLine = computed(() => ({ lineStyle: { color: c.value.border } }))
  const splitLine = computed(() => ({ lineStyle: { color: c.value.border, type: 'dashed' as const } }))
  const legendText = computed(() => ({ color: c.value.text2, fontFamily: MONO, fontSize: 10 }))
  const tooltip = computed(() => ({
    backgroundColor: c.value.panel,
    borderColor: c.value.border,
    borderWidth: 1,
    padding: [8, 10] as [number, number],
    textStyle: { color: c.value.text, fontFamily: MONO, fontSize: 11 },
    extraCssText: 'border-radius:0;box-shadow:0 12px 32px -12px rgba(0,0,0,.6)',
  }))

  /** 折线：细线、不显示拐点、面积压到 10% */
  const lineSeries = (name: string, data: number[], colorIndex = 0, area = false) => ({
    name,
    type: 'line' as const,
    data,
    showSymbol: false,
    smooth: false,
    lineStyle: { width: 1.5 },
    itemStyle: { color: palette.value[colorIndex] },
    ...(area ? { areaStyle: { opacity: 0.1, color: palette.value[colorIndex] } } : {}),
  })

  return { c, palette, axisLabel, axisLine, splitLine, legendText, tooltip, lineSeries }
}
