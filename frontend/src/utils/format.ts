/** 后端统一存 UTC（ISO 带 Z）。展示固定按东八区格式化——
 *  用固定 timeZone 而非浏览器本地时区，保证 vite-ssg 预渲染与客户端水合输出一致。 */
const TZ = 'Asia/Shanghai'

function zoned(iso: string, withTime: boolean) {
  const opts: Intl.DateTimeFormatOptions = {
    timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit', hourCycle: 'h23',
  }
  if (withTime) { opts.hour = '2-digit'; opts.minute = '2-digit' }
  const p = new Intl.DateTimeFormat('en-CA', opts).formatToParts(new Date(iso))
  const g = (t: string) => p.find((x) => x.type === t)?.value ?? ''
  const date = `${g('year')}-${g('month')}-${g('day')}`
  return withTime ? `${date} ${g('hour')}:${g('minute')}` : date
}

export function formatDate(iso: string | null | undefined): string {
  return iso ? zoned(iso, false) : ''
}

export function formatDateTime(iso: string | null | undefined): string {
  return iso ? zoned(iso, true) : ''
}

export function formatSize(bytes: number): string {
  if (bytes > 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}
