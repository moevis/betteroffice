import { expect, test } from 'bun:test';
import installedPack from '../../fonts-cjk/assets/manifest.json';
import {
  BUNDLED_FONTS,
  KAI_FAMILY,
  MISSING_CJK_FONT_ASSETS,
  STATIC_WEIGHT_SUFFIXES,
  bundledCjkFaces,
  cjkWordFamilyAliases,
  resolveBundledFamilyFace,
  resolveMetricCompatFace,
  resolveScriptFallbackFace,
  resolveStaticWeightFace,
  type BundledFontFace,
  type StaticFontWeight,
} from './manifest';

const SANS_SUFFIXES = ['Thin', 'Light', 'DemiLight', 'Regular', 'Medium', 'Bold', 'Black'] as const;
const SERIF_SUFFIXES = ['ExtraLight', 'Light', 'Regular', 'Medium', 'SemiBold', 'Bold', 'Black'] as const;
const REGIONS = ['SC', 'TC', 'JP', 'KR'] as const;
const SCRIPTS = { SC: 'cjk-sc', TC: 'cjk-tc', JP: 'cjk-jp', KR: 'cjk-kr' } as const;

const approvedFiles = [
  ...REGIONS.flatMap((region) => [
    ...SANS_SUFFIXES.map((suffix) => `NotoSans${region}-${suffix}.otf.zst`),
    ...SERIF_SUFFIXES.map((suffix) => `NotoSerif${region}-${suffix}.otf.zst`),
  ]),
  'NorthstarKai-Regular.otf.zst',
];

const shippedPack = {
  format: 1,
  schema: 1,
  pack: 'cjk',
  version: '0.5.0',
  faces: approvedFiles.map((file, index) => ({
    file,
    source: file.replace(/\.zst$/, ''),
    family: file.split('-')[0],
    codec: 'zstd',
    dict: null,
    encodedLength: index + 1,
    byteLength: (index + 1) * 1024,
    sha256: String(index).padStart(64, '0'),
  })),
};

test('builds one normal-style face per approved binary, at that binary weight and length', () => {
  const { faces, missing } = bundledCjkFaces(shippedPack);
  expect(missing).toEqual([]);
  expect(faces.map((entry) => entry.file)).toEqual(approvedFiles);
  expect(faces).toHaveLength(57);
  expect(faces.every((entry) => entry.style === 'normal')).toBe(true);
  for (const entry of faces) {
    expect(entry.byteLength).toBe((approvedFiles.indexOf(entry.file) + 1) * 1024);
  }
  for (const region of REGIONS) {
    expect(faces.filter((entry) => entry.family === `Noto Sans ${region}`).map((entry) => entry.weight))
      .toEqual([100, 300, 350, 400, 500, 700, 900]);
    expect(faces.filter((entry) => entry.family === `Noto Serif ${region}`).map((entry) => entry.weight))
      .toEqual([200, 300, 400, 500, 600, 700, 900]);
  }
  expect(faces.filter((entry) => entry.family === KAI_FAMILY).map((entry) => entry.file))
    .toEqual(['NorthstarKai-Regular.otf.zst']);
});

test('reports an ungenerated binary instead of substituting another face', () => {
  const partial = {
    ...shippedPack,
    faces: shippedPack.faces.filter((entry) => !entry.file.startsWith('NotoSerifKR')),
  };
  const { faces, missing } = bundledCjkFaces(partial);
  expect(faces.some((entry) => entry.family === 'Noto Serif KR')).toBe(false);
  expect(missing).toEqual(SERIF_SUFFIXES.map((suffix) => `NotoSerifKR-${suffix}.otf.zst`));
});

test('weight a family name spells out is selectable end to end', () => {
  const { faces } = bundledCjkFaces(shippedPack);
  const families = new Map<string, string>([
    ...faces.map((entry): [string, string] => [entry.family.toLowerCase(), entry.family]),
    ['microsoft yahei', 'Noto Sans SC'],
    ['simsun', 'Noto Serif SC'],
  ]);
  const pick = (name: string) => resolveStaticWeightFace(faces, families, name);
  expect(STATIC_WEIGHT_SUFFIXES.demilight).toBe(350);
  expect(pick('Noto Sans SC Thin')?.weight).toBe(100);
  expect(pick('Noto Sans SC Light')?.weight).toBe(300);
  expect(pick('Noto Sans SC DemiLight')?.weight).toBe(350);
  expect(pick('Noto Sans SC Medium')?.weight).toBe(500);
  expect(pick('Noto Sans SC Black')?.weight).toBe(900);
  expect(pick('Microsoft YaHei Light')?.file).toBe('NotoSansSC-Light.otf.zst');
  expect(pick('SimSun Bold')?.file).toBe('NotoSerifSC-Bold.otf.zst');
  expect(pick('Noto Serif SC SemiBold')?.file).toBe('NotoSerifSC-SemiBold.otf.zst');
  expect(pick('Noto Serif JP Black')?.file).toBe('NotoSerifJP-Black.otf.zst');
  expect(pick('Noto Sans SC ExtraBold')).toBeUndefined();
  expect(pick('Noto Sans SC Wobble')).toBeUndefined();
  expect(pick('Unknown Family Medium')).toBeUndefined();
  expect(pick('Medium')).toBeUndefined();
});

test('Mincho, Ming and Batang names follow the serif face only once it ships', () => {
  const shipped = new Set(['noto sans tc', 'noto serif tc', 'noto sans jp', 'noto sans kr', 'noto serif sc']);
  const withSerif = cjkWordFamilyAliases(shipped);
  expect(withSerif.pmingliu).toBe('pmingliu');
  expect(withSerif.mingliu).toBe('pmingliu');
  expect(withSerif['ms mincho']).toBe('ms gothic');
  expect(withSerif.batang).toBe('malgun gothic');

  const fullyShipped = cjkWordFamilyAliases(new Set([...shipped, 'noto serif jp', 'noto serif kr']));
  expect(fullyShipped['ms mincho']).toBe('ms mincho');
  expect(fullyShipped.batang).toBe('batang');
  expect(fullyShipped.gungsuh).toBe('batang');

  const absent = cjkWordFamilyAliases(new Set(['noto sans sc', 'noto serif sc']));
  expect(absent.pmingliu).toBe('microsoft jhenghei');
  expect(absent['ms mincho']).toBe('ms gothic');
  expect(absent.batang).toBe('malgun gothic');
  expect(Object.keys(fullyShipped).some((name) => name.startsWith('kaiti') || name === '楷体')).toBe(false);
});

test('default CJK rendering is the regional sans face at the requested weight', () => {
  for (const region of REGIONS) {
    const regular = resolveScriptFallbackFace(SCRIPTS[region], false, false)!;
    expect(regular.family).toBe(`Noto Sans ${region}`);
    expect(regular.weight).toBe(400);
    expect(resolveScriptFallbackFace(SCRIPTS[region], false, true)!.style).toBe('normal');
    expect(resolveBundledFamilyFace(`Noto Sans ${region}`, false, true)).toBeUndefined();
  }
});

test('installed serif and Kai mappings reach the shipped face of their own family', () => {
  const mapped: [string, string, StaticFontWeight][] = [
    ['SimSun', 'Noto Serif SC', 400],
    ['宋体', 'Noto Serif SC', 400],
    ['Noto Serif JP', 'Noto Serif JP', 400],
    ['MS Mincho', 'Noto Serif JP', 400],
    ['Batang', 'Noto Serif KR', 400],
    ['PMingLiU', 'Noto Serif TC', 400],
    ['KaiTi', KAI_FAMILY, 400],
    ['楷体', KAI_FAMILY, 400],
    ['KaiTi_GB2312', KAI_FAMILY, 400],
    ['kaiti gb2312', KAI_FAMILY, 400],
  ];
  for (const [name, family, weight] of mapped) {
    const resolved: BundledFontFace | undefined =
      resolveMetricCompatFace(name, false, false) ?? resolveBundledFamilyFace(name, false, false);
    expect(resolved?.family).toBe(family);
    expect(resolved?.weight).toBe(weight);
    expect(MISSING_CJK_FONT_ASSETS).not.toContain(resolved!.file);
  }
});

test('a bold request takes the installed bold binary, never the regular one', () => {
  for (const [name, family] of [
    ['Microsoft YaHei', 'Noto Sans SC'],
    ['SimSun', 'Noto Serif SC'],
    ['MS Mincho', 'Noto Serif JP'],
    ['Batang', 'Noto Serif KR'],
  ] as const) {
    const regular = resolveMetricCompatFace(name, false, false)!;
    const bold = resolveMetricCompatFace(name, true, false)!;
    expect(regular.family).toBe(family);
    expect(bold.family).toBe(family);
    expect(regular.weight).toBe(400);
    expect(bold.weight).toBe(700);
    expect(bold.file).not.toBe(regular.file);
  }
});

test('a name that spells a shipped weight selects that binary', () => {
  expect(resolveMetricCompatFace('Microsoft YaHei Light', false, false)?.file).toBe('NotoSansSC-Light.otf.zst');
  expect(resolveBundledFamilyFace('Noto Sans SC Medium', false, false)?.file).toBe('NotoSansSC-Medium.otf.zst');
  expect(resolveBundledFamilyFace('Noto Sans SC DemiLight', false, false)?.weight).toBe(350);
  expect(resolveBundledFamilyFace('Noto Serif SC SemiBold', false, false)?.file).toBe('NotoSerifSC-SemiBold.otf.zst');
  expect(resolveBundledFamilyFace('Noto Serif JP Black', false, false)?.file).toBe('NotoSerifJP-Black.otf.zst');
});

test('the installed pack ships every approved face, so nothing is missing', () => {
  expect(MISSING_CJK_FONT_ASSETS).toEqual([]);
  const installed = BUNDLED_FONTS.filter((entry) => entry.script?.startsWith('cjk-'));
  expect(installed.map((entry) => entry.file).sort()).toEqual([...approvedFiles].sort());
  for (const entry of installed) {
    const packed = installedPack.faces.find((candidate) => candidate.file === entry.file)!;
    expect(entry.byteLength).toBe(packed.byteLength);
    expect(entry.style).toBe('normal');
  }
});

test('CJK synthetic styles keep the selected family and real upright weight', () => {
  expect(resolveMetricCompatFace('SimSun', true, true)).toMatchObject({
    family: 'Noto Serif SC', weight: 700, style: 'normal',
  });
  expect(resolveScriptFallbackFace('cjk-sc', true, true, 'SimSun')).toMatchObject({
    family: 'Noto Serif SC', weight: 700, style: 'normal',
  });
  expect(resolveMetricCompatFace('楷体', true, true)).toMatchObject({
    family: KAI_FAMILY, weight: 400, style: 'normal',
  });
  expect(resolveScriptFallbackFace('cjk-sc', true, true, '楷体')).toMatchObject({
    family: 'Noto Serif SC', weight: 700, style: 'normal',
  });
  expect(resolveScriptFallbackFace('cjk-jp', true, true, 'Times New Roman')).toMatchObject({
    family: 'Noto Serif JP', weight: 700, style: 'normal',
  });
  expect(resolveScriptFallbackFace('cjk-sc', true, true, 'Noto Serif SC SemiBold')).toMatchObject({
    family: 'Noto Serif SC', weight: 600, style: 'normal',
  });
});
