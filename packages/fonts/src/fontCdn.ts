import { version as fontsVersion } from '../package.json';
import { version as latinVersion } from '../../fonts-latin/package.json';
import { version as intlVersion } from '../../fonts-intl/package.json';
import { version as cjkVersion } from '../../fonts-cjk/package.json';
import { getFontCdnConfiguration, setFontCdnConfiguration, type FontCdnConfiguration } from '../../../shared/office-session/fontCdn';

export type { FontCdnConfiguration } from '../../../shared/office-session/fontCdn';

export interface FontCdnOptions {
  baseUrl: string | URL | false;
  timeoutMs?: number;
}

/** @internal */
export type FontCdnPack = 'base-latin' | 'latin' | 'intl' | 'cjk';

const packagePaths: Record<FontCdnPack, { npm: string; version: string; published: string }> = {
  'base-latin': { npm: '@betteroffice/fonts', version: fontsVersion, published: `fonts/${fontsVersion}` },
  latin: { npm: '@betteroffice/fonts-latin', version: latinVersion, published: `fonts-latin/${latinVersion}` },
  intl: { npm: '@betteroffice/fonts-intl', version: intlVersion, published: `fonts-intl/${intlVersion}` },
  cjk: { npm: '@betteroffice/fonts-cjk', version: cjkVersion, published: `fonts-cjk/${cjkVersion}` },
};

/**
 * A pack file's published URL under a CDN root: `fonts[-<pack>]/<version>/assets/<file>`, matching what
 * `scripts/fonts/publish-cdn.py` uploads. Without a root it returns the npm jsDelivr layout.
 * @internal
 */
export function fontCdnAssetUrl(pack: string, file: string, baseUrl?: string): URL {
  const entry = packagePaths[pack as FontCdnPack];
  if (entry === undefined) throw new Error(`Unknown font pack: ${pack}`);
  if (baseUrl !== undefined) return new URL(`${entry.published}/assets/${file}`, baseUrl);
  return new URL(`https://cdn.jsdelivr.net/npm/${entry.npm}@${entry.version}/assets/${file}`);
}

/** @internal The decoder published beside the packs, at the configured root. */
export function fontCdnDecoderUrl(baseUrl: string): URL {
  return new URL(`fonts/${fontsVersion}/dist/decoder/fontpack.wasm`, baseUrl);
}

/**
 * Serves every bundled face from a CDN of the published layout — whole faces, sliced CJK parts, base Latin and
 * the decoder. A configured root replaces installed packs; `false` restores them. A per-call `baseUrl` still wins.
 */
export function configureFontCdn(options: FontCdnOptions): void {
  const timeoutMs = options.timeoutMs ?? 30_000;
  if (!Number.isInteger(timeoutMs) || timeoutMs <= 0 || timeoutMs > 4_294_967_295) {
    throw new RangeError('Font CDN timeoutMs must be a positive 32-bit integer');
  }
  let baseUrl: string | false = false;
  if (options.baseUrl !== false) {
    const value = String(options.baseUrl);
    const url = new URL(value.endsWith('/') ? value : `${value}/`,
      typeof location === 'undefined' ? undefined : location.href);
    if (url.protocol !== 'https:' && url.protocol !== 'http:') {
      throw new TypeError('Font CDN baseUrl must use HTTP or HTTPS');
    }
    baseUrl = url.href;
  }
  setFontCdnConfiguration({ baseUrl, timeoutMs });
}

/** @internal */
export function fontCdnConfiguration(): FontCdnConfiguration {
  return getFontCdnConfiguration() ?? { baseUrl: false, timeoutMs: 30_000 };
}
