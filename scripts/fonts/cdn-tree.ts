import { copyFile, cp, mkdir, readFile } from 'node:fs/promises';
import { dirname, join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

interface PackManifest {
  pack: string;
  version: string;
  faces: { file: string; dict: string | null; slices?: { index: string } }[];
}

function within(root: string, file: string): string {
  const path = resolve(root, file);
  if (!path.startsWith(`${resolve(root)}${sep}`)) throw new Error(`Invalid font asset path: ${file}`);
  return path;
}

export async function writeFontCdnTree(
  output: string,
  packages = fileURLToPath(new URL('../../packages/', import.meta.url)),
): Promise<void> {
  for (const name of ['fonts-latin', 'fonts-intl', 'fonts-cjk', 'fonts']) {
    const source = join(packages, name);
    const assets = join(source, 'assets');
    const manifestFile = name === 'fonts' ? 'base-latin.json' : 'manifest.json';
    const manifest = JSON.parse(await readFile(join(assets, manifestFile), 'utf8')) as PackManifest;
    let version = manifest.version;
    if (name === 'fonts') {
      const metadata: unknown = JSON.parse(await readFile(join(source, 'package.json'), 'utf8'));
      if (metadata === null || typeof metadata !== 'object' || !('version' in metadata)
        || typeof metadata.version !== 'string') throw new Error('Invalid fonts package version');
      version = metadata.version;
    }
    const target = within(output, `${name}/${version}`);
    const files = new Set([manifestFile]);
    for (const face of manifest.faces) {
      files.add(face.file);
      if (face.dict) files.add(face.dict);
      if (!face.slices) continue;
      files.add(face.slices.index);
      const index = JSON.parse(await readFile(within(assets, face.slices.index), 'utf8')) as {
        skeleton: { file: string }; core: { file: string }; chunks: { file: string }[];
      };
      for (const entry of [index.skeleton, index.core, ...index.chunks]) files.add(entry.file);
    }
    for (const file of files) {
      const destination = within(join(target, 'assets'), file);
      await mkdir(dirname(destination), { recursive: true });
      await copyFile(within(assets, file), destination);
    }
    if (name === 'fonts') {
      const decoder = 'dist/decoder/fontpack.wasm';
      const destination = within(target, decoder);
      await mkdir(dirname(destination), { recursive: true });
      await copyFile(within(source, decoder), destination);
    }
    await cp(join(source, 'LICENSES'), join(target, 'LICENSES'), { recursive: true });
    try {
      await copyFile(join(source, 'LICENSE'), join(target, 'LICENSE'));
    } catch (error) {
      if (!(error instanceof Error) || !('code' in error) || error.code !== 'ENOENT') throw error;
    }
  }
}

if (import.meta.main) {
  const output = process.argv[2];
  if (!output || process.argv.length !== 3) throw new Error('Usage: bun scripts/fonts/cdn-tree.ts <output-dir>');
  await writeFontCdnTree(output);
}
