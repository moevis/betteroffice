# @betteroffice/fonts-cjk

## 1.0.0

### Minor Changes

- de8f092: The optional CJK add-on now ships compressed `.otf.zst` assets, decoded automatically by the font manager. `CJK_FONT_ASSET_URLS` keys and `BundledFontFace.file` use the packed filenames; custom asset hosts must serve them.

### Patch Changes

- e6d5c52: Package exports now carry a `default` condition next to `import`, so webpack consumers (`next build --webpack`, including editors loaded with `next/dynamic`) resolve every entry instead of failing with "Package path is not exported".

## 0.4.2

## 0.4.1

## 0.4.0

## 0.3.0

## 0.2.0

### Patch Changes

- faa81f3: The version moves in step with `@betteroffice/fonts`; the font binaries are unchanged.

## 0.1.0

### Minor Changes

- 6be0c18: Bundled metric-compatible fonts ship as `@betteroffice/fonts`, plus `@betteroffice/fonts-cjk` for Chinese, Japanese or Korean, and DOCX uses them only when you hand the module over: `configureDefaultFonts({ fonts })`, or `configureDefaultFonts({ load: () => import('@betteroffice/fonts') })` to keep it in its own chunk. Installing the packages alone does nothing — without that call the engine reaches for no font package, measurement falls back to the browser, and pagination will not match Word. Because `@betteroffice/docx` no longer names `@betteroffice/fonts` anywhere in its published bundle, an esbuild consumer without the optional peer builds again.
