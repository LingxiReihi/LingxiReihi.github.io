import type { MediaAsset } from '@/api/types'

type Named = Pick<MediaAsset, 'storage_key' | 'filename' | 'url'>

export const extOf = (a: Named) => {
  const src = a.storage_key || a.filename || a.url || ''
  return src.slice(src.lastIndexOf('.')).toLowerCase()
}

/** 预览位只认 glb（自包含单文件，model-viewer 可直接渲染） */
export const isGlb = (a: Named) => extOf(a) === '.glb'
/** 工程压缩包：内容以层级清单展示，可整包下载 */
export const isZip = (a: Named) => extOf(a) === '.zip'

/** 可直接作为渲染图/封面上传的图片 */
export const IMAGE_EXTS = ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.avif']
/** 不单独收录的 3D 工程格式：拖进来时前端自动打包成 zip */
export const PACKABLE_EXTS = ['.gltf', '.fbx', '.obj', '.mtl', '.blend', '.max', '.usdz', '.stl',
  '.bin', '.tga', '.tif', '.tiff', '.exr', '.hdr', '.ktx2', '.dds', '.dae', '.3ds', '.ply']

export const isImageName = (name: string) => IMAGE_EXTS.some((e) => name.toLowerCase().endsWith(e))
export const isGlbName = (name: string) => name.toLowerCase().endsWith('.glb')
export const isZipName = (name: string) => name.toLowerCase().endsWith('.zip')

export interface ZipEntry { path: string; size: number }
export interface TreeNode {
  name: string
  path: string
  dir: boolean
  size?: number
  children: TreeNode[]
}

/** 把后端回传的扁平 zip 清单（含层级路径）还原为可折叠树；目录在前、按名排序 */
export function buildTree(entries: ZipEntry[]): TreeNode[] {
  const root: TreeNode = { name: '', path: '', dir: true, children: [] }
  for (const e of entries) {
    const parts = e.path.split('/').filter(Boolean)
    if (!parts.length) continue
    let node = root
    parts.forEach((p, i) => {
      const leaf = i === parts.length - 1
      const path = parts.slice(0, i + 1).join('/')
      let next = node.children.find((c) => c.name === p && c.dir === !leaf)
      if (!next) {
        next = { name: p, path, dir: !leaf, size: leaf ? e.size : undefined, children: [] }
        node.children.push(next)
      }
      node = next
    })
  }
  const sort = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => (a.dir === b.dir ? a.name.localeCompare(b.name) : a.dir ? -1 : 1))
    nodes.forEach((n) => sort(n.children))
  }
  sort(root.children)
  return root.children
}

export const treeDepth = (nodes: TreeNode[]): number =>
  nodes.length ? 1 + Math.max(...nodes.map((n) => treeDepth(n.children))) : 0

/** 工程包内可识别的主格式（越靠前越优先当作「这个包是什么」） */
const PACK_FORMATS = ['fbx', 'obj', 'blend', 'max', 'usdz', 'gltf', 'glb', 'stl', '3ds', 'dae', 'ply']

/** 从 zip 清单推断包内主格式，认不出返回 null */
export function packFormat(entries?: ZipEntry[] | null): string | null {
  if (!entries?.length) return null
  const hit = PACK_FORMATS.find((f) => entries.some((e) => e.path.toLowerCase().endsWith(`.${f}`)))
  return hit ? hit.toUpperCase() : null
}

/**
 * 下载项名称：说清「包内是什么格式」而不是容器后缀 ZIP，
 * 否则两个 zip 并排时用户无法分辨哪个是 FBX、哪个是 OBJ。
 */
export function assetKindLabel(a: MediaAsset): string {
  const ext = extOf(a).replace('.', '').toUpperCase()
  if (a.kind === 'video') return `${ext || '视频'} 视频`
  if (isZip(a)) return `${packFormat(a.entries) ?? 'ZIP'} 工程包`
  return `${ext || '模型'} 模型`
}
