import { expect, test } from 'bun:test';
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { writeFontCdnTree } from '../../../scripts/fonts/cdn-tree';

const files = ['Synthetic-Regular.ttf.zst', 'Synthetic-Bold.ttf.zst', 'Synthetic/slices.json',
  'Synthetic/skeleton.zst', 'Synthetic/core.zst', 'Synthetic/c001.zst', 'Synthetic/dict.bin'];
const packVersions = { latin: '1.2.3', intl: '2.3.4', cjk: '3.4.5' };
const fontsVersion = '9.8.7';
const baseFace = 'SyntheticBaseLatin-Regular.ttf.zst';
const licenseFiles = ['LICENSES/Synthetic.txt', 'LICENSE'];
const baseFiles = ['assets/base-latin.json', `assets/${baseFace}`, 'dist/decoder/fontpack.wasm'];
const publications = [
  ...Object.entries(packVersions).map(([pack, version]) => ({
    name: `fonts-${pack}`, version,
    files: [...files.map((file) => `assets/${file}`), 'assets/manifest.json', ...licenseFiles],
  })),
  { name: 'fonts', version: fontsVersion, files: [...baseFiles, ...licenseFiles] },
];

async function fixture(root: string): Promise<void> {
  for (const [pack, version] of Object.entries(packVersions)) {
    const source = join(root, `fonts-${pack}`);
    for (const file of files) {
      const path = join(source, 'assets', file);
      await mkdir(dirname(path), { recursive: true });
      await writeFile(path, file.endsWith('.json') ? JSON.stringify({
        skeleton: { file: files[3] }, core: { file: files[4] }, chunks: [{ file: files[5] }],
      }) : new Uint8Array([1, 2, 3]));
    }
    await writeFile(join(source, 'assets/manifest.json'), JSON.stringify({
      pack, version, faces: [
        { file: files[0], dict: null, slices: { index: files[2] } },
        { file: files[1], dict: files[6] },
      ],
    }));
    await writeFile(join(source, 'package.json'), JSON.stringify({ name: `@betteroffice/fonts-${pack}`, version }));
  }
  const source = join(root, 'fonts');
  await mkdir(join(source, 'assets'), { recursive: true });
  await writeFile(join(source, 'assets/base-latin.json'), JSON.stringify({
    pack: 'base-latin', version: '1', faces: [{ file: baseFace, dict: null }],
  }));
  await writeFile(join(source, 'assets', baseFace), new Uint8Array([4, 5, 6]));
  await writeFile(join(source, 'package.json'), JSON.stringify({ name: '@betteroffice/fonts', version: fontsVersion }));
  await mkdir(join(source, 'dist/decoder'), { recursive: true });
  await writeFile(join(source, 'dist/decoder/fontpack.wasm'), new Uint8Array([7, 8, 9]));
  for (const { name } of publications) {
    await mkdir(join(root, name, 'LICENSES'));
    await writeFile(join(root, name, 'LICENSES/Synthetic.txt'), `${name} license`);
    await writeFile(join(root, name, 'LICENSE'), `${name} package license`);
  }
}

async function treeFiles(directory: string): Promise<string[]> {
  const files: string[] = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      for (const file of await treeFiles(join(directory, entry.name))) files.push(`${entry.name}/${file}`);
    } else {
      files.push(entry.name);
    }
  }
  return files.sort();
}

test('the self-hosted tree exactly matches all four published packages, including base Latin and the decoder', async () => {
  const root = await mkdtemp(join(tmpdir(), 'font-cdn-synthetic-'));
  try {
    const packages = join(root, 'packages');
    const output = join(root, 'output');
    await fixture(packages);
    await writeFontCdnTree(output, packages);
    const expected: string[] = [];
    for (const { name, version, files } of publications) {
      for (const file of files) {
        const published = `${name}/${version}/${file}`;
        expected.push(published);
        expect(await readFile(join(output, published))).toEqual(await readFile(join(packages, name, file)));
      }
    }
    expect(await treeFiles(output)).toEqual(expected.sort());
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('package LICENSE files may be absent while LICENSES directories remain required', async () => {
  const root = await mkdtemp(join(tmpdir(), 'font-cdn-licenses-'));
  try {
    const packages = join(root, 'packages');
    const output = join(root, 'output');
    await fixture(packages);
    for (const { name } of publications) await rm(join(packages, name, 'LICENSE'));
    await writeFontCdnTree(output, packages);
    expect(await treeFiles(output)).toEqual(publications.flatMap(({ name, version, files }) => files
      .filter((file) => file !== 'LICENSE')
      .map((file) => `${name}/${version}/${file}`)).sort());
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('a missing face, dictionary, slice, license directory, manifest or decoder fails the export', async () => {
  const missingFiles = publications.flatMap(({ name, files }) => [
    ...files.filter((file) => !licenseFiles.includes(file)), 'LICENSES',
  ].map((file) => `${name}/${file}`));
  for (const file of [...missingFiles, 'fonts/package.json']) {
    const root = await mkdtemp(join(tmpdir(), 'font-cdn-missing-'));
    try {
      const packages = join(root, 'packages');
      await fixture(packages);
      await rm(join(packages, file), { recursive: true });
      await expect(writeFontCdnTree(join(root, 'output'), packages)).rejects.toThrow();
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  }
});
