# Font pack tooling

Install the release tooling in a virtual environment:

```sh
python3 -m venv /tmp/fontpack-venv
/tmp/fontpack-venv/bin/pip install fonttools==4.60.1 brotli==1.1.0
/tmp/fontpack-venv/bin/python scripts/fonts/woff2-transform.py <ttf-directory>
```

The transform writes `.uw2` (identity table stream) and standard `.woff2`
companions beside each `.ttf`, with fixed head timestamps. Both transform only
`glyf` and `loca`. It also writes `<face>.source.sha256`, which lists the SHA-256
of the exact `.ttf` bytes encoded and of both companions, in `sha256sum` format.
Use `fontpack build --codec woff2t` to compress and verify them; the builder
requires a matching sidecar for every face. Regenerate companions with
`scripts/fonts/woff2-transform.py` whenever a TTF changes.
The binary is in `betteroffice-fonts`, behind its `build` feature:

```sh
cargo run -p betteroffice-fonts --features build --bin fontpack -- build --src <directory> --out <pack-directory>
```

The default builder codec remains `zstd`; CFF/OTF faces use that codec.
This tooling runs only during development or release preparation. It never
fetches dependencies or runs at package installation.

## CJK pack

The source lock covers the seven official static weights of regional Noto Sans
and Serif (SC, TC, JP, KR), plus LXGW ZhenKai GB and both upstream licenses.
`fetch-cjk.sh` verifies every SHA-256, downloads with bounded parallelism and
reuses verified files from `FONT_SOURCE_CACHE`. It converts the pinned ZhenKai
TTF into the renamed static `Northstar Kai` CFF face and records provenance.

```sh
cargo build --release -p betteroffice-fonts --features build --bin fontpack
PYTHON=/tmp/fontpack-venv/bin/python FONT_SOURCE_CACHE=.source/font-source-cache \
  scripts/fonts/build-cjk.sh .source/font-release/fonts-cjk
bun scripts/fonts/generate-cjk-urls.ts .source/font-release/fonts-cjk/assets .source/font-release/fonts-cjk/src/index.ts
```

The output directory must not exist. For offline input, use
`fetch-cjk.sh <directory> <local-source-directory>`; local sources receive the
same hash checks. `sources.json` records source pins, conversion hashes and
licenses. No source fetch runs during package installation.

Before building, cut each face into a skeleton and outline chunks (same pinned
fontTools as above):

```sh
/tmp/fontpack-venv/bin/python scripts/fonts/cjk-slices.py <dir>
/tmp/fontpack-venv/bin/python scripts/fonts/test_cjk_slices.py
```

The second command checks the cutter on a small synthetic CID-keyed face.

It writes `<face>.slices/` and `<face>.slices.sha256` beside each OTF. The
skeleton keeps every table of the face byte for byte except `CFF `, whose
CharStrings INDEX is cut off; each chunk holds desubroutinized charstrings by
glyph id, ordered by Google's frequency-ranked slicing strategies in
`nam-slices` (Apache License 2.0), with slices 1 to 20 merged into a core.
The script checks that every chunk holds the GSUB closure of its codepoints and
that the reassembled face keeps every other table and charstring; `fontpack`
then compresses the files to `assets/<face>/`, checks that its own reassembly
matches, and adds a `slices` block to the face's manifest row.

## Versioned CDN publication

Run the `Font CDN assets` workflow after selecting the font package version.
Its build job produces the static CJK pack from the source lock, stages the
Latin and international packs, and builds the matching manager decoder. Source
downloads are cached across runs but always hash-checked. Publication is an explicit
workflow input and uses the `font-cdn` environment. Configure required reviewers
there, secrets `TOS_ACCESS_KEY` / `TOS_SECRET_KEY`, and environment variables
`TOS_ENDPOINT`, `TOS_REGION`, `TOS_BUCKET`.

`publish-cdn.py <package-directory> --publish --verify` publishes all four package
directories from the CI artifact: `fonts-cjk/<version>/assets/...`,
`fonts-latin/<version>/assets/...`, `fonts-intl/<version>/assets/...`, and
`fonts/<version>/assets/...`, with licenses under each package version. The decoder
is `fonts/<version>/dist/decoder/fontpack.wasm`. Versions come from each package's
`package.json`, not from the application release.

Different bytes at an existing object key are refused. Identical objects are reused
only if their stored cache metadata also satisfies the immutable resource policy;
publication never overwrites them. Binaries precede slice indexes and each pack's
manifest. The final check reads every CDN object and verifies encoded length,
SHA-256, matching CORS, and `Cache-Control: public, max-age=31536000, immutable`
(a longer max-age is allowed; private/no-cache/no-store are refused).
Do not deploy a consumer configured for these versions until publication and CDN
verification pass. In the application, configure the CDN root before editor/session
initialization; do not replace this pipeline with Go-hosted font assets.

Application CI installs pinned packages; it does not fetch upstream fonts or
publish the font CDN on every application build.

