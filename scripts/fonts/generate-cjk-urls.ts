import { mkdir, readFile, stat, writeFile } from 'node:fs/promises';
import { dirname, resolve, sep } from 'node:path';

export async function generateCjkUrls(assets: string, output: string): Promise<void> {
  const root = resolve(assets);
  const inside = (file: string) => {
    const path = resolve(root, file);
    if (!path.startsWith(root + sep)) throw new Error(`Invalid CJK asset path: ${file}`);
    return path;
  };
  const manifest = JSON.parse(await readFile(inside('manifest.json'), 'utf8')) as {
    faces: { file: string; dict?: string | null; slices?: { index: string } }[];
  };
  const files = new Set<string>();
  for (const face of manifest.faces) {
    files.add(face.file);
    if (face.dict) files.add(face.dict);
    if (!face.slices) throw new Error(`CJK face has no slices: ${face.file}`);
    files.add(face.slices.index);
    const index = JSON.parse(await readFile(inside(face.slices.index), 'utf8')) as {
      skeleton: { file: string }; core: { file: string }; chunks: { file: string }[];
    };
    for (const part of [index.skeleton, index.core, ...index.chunks]) files.add(part.file);
  }
  for (const file of files) {
    if (!(await stat(inside(file))).isFile()) throw new Error(`Missing CJK font resource: ${file}`);
  }
  const entries = [...files].sort().map(file =>
    `  ${JSON.stringify(file)}: () => new URL(${JSON.stringify(`../assets/${file}`)}, import.meta.url),`);
  await mkdir(dirname(resolve(output)), { recursive: true });
  await writeFile(output, `export const CJK_FONT_ASSET_URLS: Record<string, () => URL> = {\n${entries.join('\n')}\n};\n`);
}

if (import.meta.main) {
  const [assets, output, extra] = process.argv.slice(2);
  if (!assets || !output || extra) throw new Error('Usage: bun scripts/fonts/generate-cjk-urls.ts <assets-directory> <index.ts>');
  await generateCjkUrls(assets, output);
}
