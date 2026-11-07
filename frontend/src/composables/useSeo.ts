import { useHead } from '@unhead/vue'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { fallback, useSiteStore } from '@/stores/site'

interface SeoInput {
  title: MaybeRefOrGetter<string>
  siteTitle?: MaybeRefOrGetter<string | undefined>
  description?: MaybeRefOrGetter<string | undefined | null>
  path: MaybeRefOrGetter<string>
  image?: MaybeRefOrGetter<string | null | undefined>
  type?: 'website' | 'article'
  jsonLd?: MaybeRefOrGetter<Record<string, unknown> | undefined>
}

/** SEO 页面规范（docs/frontend-design.md §10.2）：title/description/canonical/og/JSON-LD。 */
export function useSeo(o: SeoInput) {
  const origin = typeof window !== 'undefined'
    ? window.location.origin
    : (import.meta.env.VITE_SITE_ORIGIN ?? '')

  const full = computed(() => {
    const t = toValue(o.title)
    let s = o.siteTitle ? toValue(o.siteTitle) : ''
    if (!s) {
      try {
        s = (useSiteStore().config ?? fallback).site.title
      } catch { /* pinia 未就绪 */ }
    }
    return s ? `${t} · ${s}` : t
  })
  const desc = computed(() => toValue(o.description) ?? '')
  const url = computed(() => `${origin}${toValue(o.path)}`)
  const image = computed(() => {
    const i = o.image ? toValue(o.image) : null
    return i ? `${origin}${i}` : ''
  })

  useHead({
    title: full,
    meta: computed(() => [
      { name: 'description', content: desc.value },
      { property: 'og:title', content: full.value },
      { property: 'og:description', content: desc.value },
      { property: 'og:url', content: url.value },
      { property: 'og:type', content: o.type ?? 'website' },
      ...(image.value ? [{ property: 'og:image', content: image.value }] : []),
      { name: 'twitter:card', content: image.value ? 'summary_large_image' : 'summary' },
    ]),
    link: computed(() => [{ rel: 'canonical', href: url.value }]),
    script: computed(() => {
      const ld = o.jsonLd ? toValue(o.jsonLd) : undefined
      return ld ? [{ type: 'application/ld+json' as const, innerHTML: JSON.stringify(ld) }] : []
    }),
  })
}
