import { computed } from 'vue'
import { darkTheme, type GlobalThemeOverrides } from 'naive-ui'

import { useThemeStore } from '@/stores/theme'

/**
 * 后台统一的 Naive UI 主题：跟前台「仪器面板」HUD 对齐 —— 直角、面板色、主色描边。
 * 登录页与 AdminLayout 共用，避免两处各写一份主题导致观感不一致。
 */
export function useAdminTheme() {
  const theme = useThemeStore()
  const dark = computed(() => theme.mode === 'dark')
  const naiveTheme = computed(() => (dark.value ? darkTheme : null))

  const themeOverrides = computed<GlobalThemeOverrides>(() => {
    const c = dark.value
      ? {
          bg: '#0b1220', sider: '#0d1524', panel: '#0f1826', raised: '#16223a',
          border: '#1f2c47', text: '#e6edf3', text2: '#9fb0c3', text3: '#5f7185',
          primary: '#39c5bb', primaryHover: '#5ee0d6', primaryPressed: '#2ea79f',
          hover: 'rgba(57,197,187,0.08)', active: 'rgba(57,197,187,0.16)',
        }
      : {
          bg: '#f8fafc', sider: '#ffffff', panel: '#ffffff', raised: '#f1f5f9',
          border: '#e2e8f0', text: '#0f172a', text2: '#475569', text3: '#94a3b8',
          primary: '#0d9488', primaryHover: '#14b8a6', primaryPressed: '#0f766e',
          hover: 'rgba(13,148,136,0.07)', active: 'rgba(13,148,136,0.14)',
        }

    return {
      common: {
        primaryColor: c.primary,
        primaryColorHover: c.primaryHover,
        primaryColorPressed: c.primaryPressed,
        primaryColorSuppl: c.primaryHover,
        // HUD 基调：一律直角
        borderRadius: '0',
        borderRadiusSmall: '0',
        bodyColor: c.bg,
        cardColor: c.panel,
        modalColor: c.panel,
        popoverColor: c.panel,
        tableColor: c.panel,
        inputColor: c.panel,
        borderColor: c.border,
        dividerColor: c.border,
        textColorBase: c.text,
        textColor1: c.text,
        textColor2: c.text2,
        textColor3: c.text3,
        placeholderColor: c.text3,
        hoverColor: c.hover,
        fontSize: '13px',
        fontWeightStrong: '600',
      },
      Layout: {
        color: c.bg,
        siderColor: c.sider,
        siderBorderColor: c.border,
        headerColor: c.sider,
      },
      Menu: {
        borderRadius: '0',
        itemHeight: '38px',
        itemColorHover: c.hover,
        itemColorActive: c.active,
        itemColorActiveHover: c.active,
        itemTextColor: c.text2,
        itemTextColorHover: c.text,
        itemTextColorActive: c.primary,
        itemTextColorActiveHover: c.primary,
        itemIconColor: c.text3,
        itemIconColorHover: c.text,
        itemIconColorActive: c.primary,
        itemIconColorActiveHover: c.primary,
      },
      Card: { borderRadius: '0', color: c.panel, borderColor: c.border, paddingMedium: '16px 18px' },
      Button: {
        borderRadiusTiny: '0', borderRadiusSmall: '0', borderRadiusMedium: '0', borderRadiusLarge: '0',
        fontWeight: '500',
      },
      Input: { borderRadius: '0' },
      InputNumber: { peers: { Input: { borderRadius: '0' } } },
      Select: { peers: { InternalSelection: { borderRadius: '0' } } },
      DatePicker: { peers: { Input: { borderRadius: '0' } } },
      Tag: { borderRadius: '0' },
      DataTable: {
        borderRadius: '0',
        thColor: c.raised,
        thTextColor: c.text2,
        thFontWeight: '500',
        tdColor: c.panel,
        tdColorHover: c.hover,
        tdColorStriped: c.bg,
        borderColor: c.border,
      },
      Pagination: { itemBorderRadius: '0' },
      Dialog: { borderRadius: '0' },
      Popover: { borderRadius: '0' },
      Dropdown: { borderRadius: '0' },
      Message: { borderRadius: '0' },
      Alert: { borderRadius: '0' },
      Checkbox: { borderRadius: '0' },
      Switch: { railBorderRadius: '0', buttonBorderRadius: '0' },
    }
  })

  return { naiveTheme, themeOverrides }
}
