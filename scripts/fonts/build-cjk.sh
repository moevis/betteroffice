#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 1 ]]; then
  echo 'Usage: build-cjk.sh <new-output-package-directory>' >&2
  exit 1
fi
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
out="$(realpath -m "$1")"
if [[ -e "$out" ]]; then
  echo "Refusing to replace existing output: $out" >&2
  exit 1
fi
python="${PYTHON:-python3}"
packer="${FONT_PACKER:-$root/target/release/fontpack}"
if [[ ! -x "$packer" ]]; then
  echo 'Build fontpack first: cargo build --release -p betteroffice-fonts --features build --bin fontpack' >&2
  exit 1
fi
version="$("$python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$root/packages/fonts-cjk/package.json")"
mkdir -p "$root/.source"
work="$(mktemp -d "$root/.source/cjk-build.XXXXXXXX")"
trap 'rm -rf "$work"' EXIT
export FONT_SOURCE_CACHE="${FONT_SOURCE_CACHE:-$root/.source/font-source-cache}"
"$root/scripts/fonts/fetch-cjk.sh" "$work/sources"
# The application CDN profile keeps regional sans/serif regular and bold faces,
# plus the Simplified-Chinese Kai fallback. The source lock remains complete so
# other consumers can still regenerate the full pack when needed.
keep=(
  NotoSansSC-Regular.otf NotoSansSC-Bold.otf
  NotoSansJP-Regular.otf NotoSansJP-Bold.otf
  NotoSansKR-Regular.otf NotoSansKR-Bold.otf
  NotoSerifSC-Regular.otf NotoSerifSC-Bold.otf
  NotoSerifJP-Regular.otf NotoSerifJP-Bold.otf
  NotoSerifKR-Regular.otf NotoSerifKR-Bold.otf
  NorthstarKai-Regular.otf OFL-Noto-CJK.txt OFL-ZhenKai.txt
)
for path in "$work/sources"/*; do
  name="${path##*/}"
  case " ${keep[*]} " in
    *" $name "*) ;;
    *) rm -rf -- "$path" ;;
  esac
done
"$python" "$root/scripts/fonts/cjk-slices.py" "$work/sources"
mkdir -p "$work/package"
"$packer" build --src "$work/sources" --out "$work/package/assets" --pack cjk --version "$version" --codec zstd
cp "$root/packages/fonts-cjk/package.json" "$work/package/package.json"
cp "$root/packages/fonts-cjk/LICENSE" "$work/package/LICENSE"
cp -R "$root/packages/fonts-cjk/LICENSES" "$work/package/LICENSES"
cp "$work/sources/OFL-ZhenKai.txt" "$work/package/LICENSES/OFL-ZhenKai.txt"
cp "$work/sources/OFL-Noto-CJK.txt" "$work/package/LICENSES/OFL-Noto-CJK.txt"
cp "$work/sources/sources.json" "$work/package/LICENSES/SOURCES.json"
cp "$root/scripts/fonts/cjk-sources.sha256" "$work/package/LICENSES/cjk-sources.sha256"
cp "$root/scripts/fonts/cjk-sources.env" "$work/package/LICENSES/cjk-sources.env"
mkdir -p "$(dirname "$out")"
mv "$work/package" "$out"
echo "CJK font package prepared: $out"
