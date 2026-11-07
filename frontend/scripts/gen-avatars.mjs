// 评论区本地头像图包生成器：DiceBear Open Peeps（设计 CC0 1.0，作者 Pablo Stanley）。
// 用法：node scripts/gen-avatars.mjs [张数]   默认 60
// 张数必须与 backend/app/core/text.py 的 AVATAR_COUNT 一致，tests/test_comment_avatars.py 会钉住这条。
// seed 固定，重跑得到完全相同的图包；换风格改 STYLE 与 BG 即可。
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createAvatar } from '@dicebear/core';
import * as openPeeps from '@dicebear/open-peeps';

const COUNT = Number(process.argv[2] ?? 60);
const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'avatars');

// 浅粉彩底：Open Peeps 是黑色线稿，深底站和亮底站都要看得清，所以底色一律给浅。
// 不要传 backgroundType：v9 的 open-peeps 遇到它会渲染成空图（只剩背景矩形）。
const BG = ['d9f2ef', 'e6dff2', 'f3d9c6', 'cfe3f5', 'ddefd9', 'f5e0a3', 'dfe3c8', 'f9c6c1'];

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });
for (let i = 0; i < COUNT; i += 1) {
  const svg = createAvatar(openPeeps, {
    seed: `personal-web-${i}`,
    size: 128,
    backgroundColor: BG,
  }).toString();
  if (!svg.includes('<path')) throw new Error(`seed personal-web-${i} 渲染为空图，检查选项`);
  writeFileSync(join(OUT, `${String(i).padStart(2, '0')}.svg`), svg);
}
console.log(`[avatars] ${COUNT} 张 → ${OUT}`);
