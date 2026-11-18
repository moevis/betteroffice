#!/usr/bin/env bash
# Fetches the static CJK faces the font pack is built from.
#
# Every file is pinned: noto-cjk sources by commit, ZhenKai by release tag, all
# of them by SHA-256 in cjk-sources.sha256. Downloads run in bounded parallel;
# a cached copy is reused only after its SHA-256 matches the lock. The output
# directory holds faces ready for cjk-slices.py and fontpack, including the
# NorthstarKai-Regular.otf converter output. Nothing here runs at package
# installation time.
#
# Usage: fetch-cjk.sh <output-directory> [local-source-directory]
#
# Environment: PYTHON=<interpreter with fontTools 4.60.1> (default python3),
# FONT_SOURCE_CACHE=<directory of verified raw sources>,
# FONT_SOURCE_JOBS=<1-16 parallel downloads, default 6>.
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo 'Usage: fetch-cjk.sh <output-directory> [local-source-directory]' >&2
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
checksums="$script_dir/cjk-sources.sha256"
# shellcheck source=cjk-sources.env
. "$script_dir/cjk-sources.env"
SANS_COMMIT="$NOTO_SANS_COMMIT"
SERIF_COMMIT="$NOTO_SERIF_COMMIT"
if [[ ! "$SANS_COMMIT" =~ ^[a-fA-F0-9]{40}$ || ! "$SERIF_COMMIT" =~ ^[a-fA-F0-9]{40}$ ]]; then
  echo 'Fill NOTO_SANS_COMMIT and NOTO_SERIF_COMMIT with verified noto-cjk commits first.' >&2
  exit 1
fi
if [[ ! "$KAI_RELEASE" =~ ^v[0-9]+(\.[0-9]+){1,2}$ || ! "$KAI_COMMIT" =~ ^[a-fA-F0-9]{40}$ ]]; then
  echo 'Fill KAI_RELEASE and KAI_COMMIT with a verified LxgwZhenKai release first.' >&2
  exit 1
fi
jobs="${FONT_SOURCE_JOBS:-6}"
cache="${FONT_SOURCE_CACHE:-}"
python="${PYTHON:-python3}"
if [[ ! "$jobs" =~ ^[0-9]+$ ]] || (( jobs < 1 || jobs > 16 )); then
  echo 'FONT_SOURCE_JOBS must be an integer from 1 to 16.' >&2
  exit 1
fi

regions=(SC TC JP KR)
sans_styles=(Thin Light DemiLight Regular Medium Bold Black)
serif_styles=(ExtraLight Light Regular Medium SemiBold Bold Black)
expected=()
for region in "${regions[@]}"; do
  for style in "${sans_styles[@]}"; do expected+=("NotoSans$region-$style.otf"); done
done
for region in "${regions[@]}"; do
  for style in "${serif_styles[@]}"; do expected+=("NotoSerif$region-$style.otf"); done
done
expected+=("$KAI_ASSET" "OFL-Noto-CJK.txt" "OFL-ZhenKai.txt")

url_for() {
  local name="$1" rest region
  case "$name" in
    NotoSansSC-*.otf | NotoSansTC-*.otf | NotoSansJP-*.otf | NotoSansKR-*.otf)
      rest="${name#NotoSans}"
      region="${rest%%-*}"
      printf 'https://raw.githubusercontent.com/notofonts/noto-cjk/%s/Sans/SubsetOTF/%s/%s' \
        "$SANS_COMMIT" "$region" "$name"
      ;;
    NotoSerifSC-*.otf | NotoSerifTC-*.otf | NotoSerifJP-*.otf | NotoSerifKR-*.otf)
      rest="${name#NotoSerif}"
      region="${rest%%-*}"
      printf 'https://raw.githubusercontent.com/notofonts/noto-cjk/%s/Serif/SubsetOTF/%s/%s' \
        "$SERIF_COMMIT" "$region" "$name"
      ;;
    "$KAI_ASSET")
      printf 'https://github.com/lxgw/LxgwZhenKai/releases/download/%s/%s' "$KAI_RELEASE" "$name"
      ;;
    OFL-Noto-CJK.txt)
      printf 'https://raw.githubusercontent.com/notofonts/noto-cjk/%s/LICENSE' "$SANS_COMMIT"
      ;;
    OFL-ZhenKai.txt)
      printf 'https://raw.githubusercontent.com/lxgw/LxgwZhenKai/%s/OFL.txt' "$KAI_COMMIT"
      ;;
    *)
      return 1
      ;;
  esac
}

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -- "$1" | cut -d' ' -f1
  else
    shasum -a 256 -- "$1" | cut -d' ' -f1
  fi
}

digest_of() {
  local name="$1" digest listed extra
  while read -r digest listed extra; do
    if [[ "$listed" == "$name" ]]; then
      printf '%s' "$digest"
      return 0
    fi
  done < "$checksums"
  return 1
}

digests=()
names=()
seen=' '
while read -r digest name extra; do
  if [[ -z "${digest:-}" && -z "${name:-}" ]]; then
    continue
  fi
  if [[ ! "$digest" =~ ^[a-fA-F0-9]{64}$ || -z "${name:-}" || -n "${extra:-}" ]]; then
    echo "Invalid or unfilled SHA-256 entry: ${digest:-} ${name:-}" >&2
    exit 1
  fi
  case " ${expected[*]} " in
    *" $name "*) ;;
    *) echo "Unexpected source: $name" >&2; exit 1 ;;
  esac
  case "$seen" in
    *" $name "*) echo "Duplicate source: $name" >&2; exit 1 ;;
  esac
  seen="$seen$name "
  digests+=("$digest")
  names+=("$name")
done < "$checksums"

if (( ${#names[@]} != ${#expected[@]} )); then
  echo "cjk-sources.sha256 lists ${#names[@]} sources, expected ${#expected[@]}." >&2
  exit 1
fi
for name in "${expected[@]}"; do
  case "$seen" in
    *" $name "*) ;;
    *) echo "Missing SHA-256 entry: $name" >&2; exit 1 ;;
  esac
done

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

if [[ $# -eq 2 ]]; then
  for index in "${!names[@]}"; do
    name="${names[$index]}"
    if ! cp "$2/$name" "$work_dir/$name" 2>/dev/null; then
      echo "Failed to copy local CJK font: $name" >&2
      exit 1
    fi
    if [[ "$(hash_file "$work_dir/$name")" != "${digests[$index]}" ]]; then
      echo "CJK source SHA-256 mismatch for $name (local copy)." >&2
      exit 1
    fi
  done
else
  export work_dir cache checksums
  export SANS_COMMIT SERIF_COMMIT KAI_RELEASE KAI_COMMIT KAI_ASSET
  export -f url_for hash_file digest_of
  fetch() {
    local name="$1" url part
    url="$(url_for "$name")" || { echo "No pinned URL for $name" >&2; return 1; }
    if [[ -n "$cache" && -f "$cache/$name" ]]; then
      if [[ "$(hash_file "$cache/$name")" == "$(digest_of "$name")" ]]; then
        cp "$cache/$name" "$work_dir/$name"
        return 0
      fi
      rm -f "$cache/$name"
    fi
    part="$work_dir/.$name.part"
    if ! curl --fail --location --retry 3 --proto '=https' --tlsv1.2 --output "$part" "$url"; then
      echo "Failed to download CJK font: $name" >&2
      rm -f "$part"
      return 1
    fi
    mv "$part" "$work_dir/$name"
  }
  export -f fetch

  if ! printf '%s\0' "${names[@]}" | xargs -0 -P "$jobs" -n 1 bash -c 'fetch "$0"'; then
    echo 'CJK source download failed.' >&2
    exit 1
  fi
fi

if ! (
  cd "$work_dir"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum --check "$checksums"
  else
    shasum -a 256 --check "$checksums"
  fi
); then
  echo 'CJK source SHA-256 verification failed.' >&2
  exit 1
fi

if [[ -n "$cache" ]]; then
  mkdir -p "$cache"
  for name in "${names[@]}"; do
    if [[ -f "$cache/$name" ]]; then
      continue
    fi
    cp "$work_dir/$name" "$cache/.$name.$$"
    mv "$cache/.$name.$$" "$cache/$name"
  done
fi

mkdir -p "$1"
"$python" "$script_dir/prepare-cjk.py" "$work_dir" "$1"

echo "Verified ${#names[@]} CJK sources and wrote ready-to-cut faces to $1"
