# @betteroffice/fonts-cjk

Chinese, Japanese and Korean faces for [`@betteroffice/fonts`](https://www.npmjs.com/package/@betteroffice/fonts).
Static faces and their glyph slices load on demand; installing the pack does not preload every weight.

## Install

```bash
bun add @betteroffice/fonts @betteroffice/fonts-cjk
```

## Usage

No import from this package is needed. Install it next to `@betteroffice/fonts` and configure that
package once; it loads these faces through an optional dynamic import.

```ts
import { configureDefaultFonts } from '@betteroffice/docx/layout';
import * as fonts from '@betteroffice/fonts';

configureDefaultFonts({ fonts });
```

The `@betteroffice/fonts/cdn` entry loads the CJK faces from a CDN without installing this package.

## Contents

| Family | Region | Static upright weights |
| --- | --- | --- |
| Noto Sans SC / TC / JP / KR | Simplified Chinese, Traditional Chinese, Japanese, Korean | Thin, Light, DemiLight, Regular, Medium, Bold, Black |
| Noto Serif SC / TC / JP / KR | Simplified Chinese, Traditional Chinese, Japanese, Korean | ExtraLight, Light, Regular, Medium, SemiBold, Bold, Black |
| Northstar Kai | Simplified Chinese Kai fallback derived from LXGW ZhenKai GB | Regular |

The default CJK coverage face is the regional Noto Sans; serif requests use Noto Serif and Kai requests use Northstar Kai. Existing document font declarations are preserved. These are static fonts, not runtime variable fonts. CJK italic uses upright outlines with renderer synthesis, not a separately designed italic face.

## API

```ts
import { CJK_FONT_ASSET_URLS } from '@betteroffice/fonts-cjk';
```

`CJK_FONT_ASSET_URLS` maps each `<Face>.otf.zst` filename, as named in the
`@betteroffice/fonts` manifest, to a `() => URL` resolver with a literal asset path
for bundlers. Hosts do not normally import it.

## Assets

The package ships font pack format 1: one Zstandard frame per face and a schema 1
`assets/manifest.json` recording `codec`, `dict`, `sha256`, `encodedLength` and
decoded `byteLength`. These CFF faces use `zstd`; non-Regular whole faces can
reference their family's Regular dictionary. Slices decode independently. The
font manager verifies integrity and returns independently owned sfnt buffers.

For a custom `baseUrl`, copy the packed assets alongside the other font packs and
serve `node_modules/@betteroffice/fonts/dist/decoder/fontpack.wasm` at
`<baseUrl>/decoder/fontpack.wasm` as `application/wasm`.

## Documentation

- [`@betteroffice/fonts`](https://www.npmjs.com/package/@betteroffice/fonts)
- [`@betteroffice/fonts-intl`](https://www.npmjs.com/package/@betteroffice/fonts-intl)
- [Packages and fonts](https://docs.betteroffice.dev/docs/packages#fonts)

## Licensing

Loader code is Apache-2.0 (see `LICENSE`). Fonts use the SIL Open Font License
1.1; `LICENSES/OFL-NotoCJK.txt` carries the license and copyright notices. The order of
the outline chunks in `assets/<face>/` comes from Google's CJK slicing strategies
(googlefonts/nam-files), Apache License 2.0, in
`LICENSES/Apache-2.0-nam-files.txt`.
Static Noto `SubsetOTF` sources come from
[notofonts/noto-cjk](https://github.com/notofonts/noto-cjk), with Sans pinned to
`523d033d6cb47f4a80c58a35753646f5c3608a78` and Serif to
`9b0f1436e455d902de067a2501422e5dc71ad16b`.
Northstar Kai is converted from LXGW ZhenKai GB v0.825 and renamed to avoid its
reserved font names. `LICENSES/OFL-ZhenKai.txt` and `LICENSES/SOURCES.json` retain
the upstream license, source hashes and conversion attribution.
