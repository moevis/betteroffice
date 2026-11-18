#!/usr/bin/env python3
"""Assembles the verified CJK sources into the faces `fontpack` builds from.

`<source-directory>` is what `fetch-cjk.sh` writes: the 56 noto-cjk static OTF
faces, the pinned ZhenKai TrueType source and both licence texts, every byte
checked against `cjk-sources.sha256`. `<build-directory>` receives the same Noto
faces under their shipped names, the same licence texts, and the Kai derivative
`NorthstarKai-Regular.otf`, converted from TrueType to CFF by `ttf-to-cff.py`.
Its `sources.json` records the pins, the licences and the conversion, so a rerun
rebuilds only what is missing or changed.

`fontpack build --src <build-directory>` then packs these faces; nothing here
fetches, and nothing here runs at package installation time.

Usage: prepare-cjk.py <source-directory> <build-directory> [--force]
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

FONTTOOLS_VERSION = "4.60.1"
FORMAT = 2
LICENSES = ("OFL-Noto-CJK.txt", "OFL-ZhenKai.txt")
KAI = {
    "file": "NorthstarKai-Regular.otf",
    "ps_name": "NorthstarKai-Regular",
    "family": "Northstar Kai",
    "style": "Regular",
    "modified": "2026-03-17",
}


def pins(script_dir):
    values = {}
    for line in (script_dir / "cjk-sources.env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        values[key] = value
    for key in ("NOTO_SANS_COMMIT", "NOTO_SERIF_COMMIT", "KAI_RELEASE", "KAI_COMMIT", "KAI_ASSET"):
        if not values.get(key):
            raise SystemExit(f"cjk-sources.env has no {key}")
    return values


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lock(script_dir):
    path = script_dir / "cjk-sources.sha256"
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        hash_value, name = line.split("  ")
        if len(hash_value) != 64:
            raise SystemExit(f"invalid SHA-256 entry in {path.name}: {line}")
        entries.append((name, hash_value))
    if not entries:
        raise SystemExit(f"{path.name} lists no sources")
    return entries


def sources(entries, source_dir):
    available = {}
    for name, expected in entries:
        path = source_dir / name
        if not path.is_file():
            raise SystemExit(f"missing CJK source: {path}")
        actual = digest(path)
        if actual != expected:
            raise SystemExit(f"CJK source SHA-256 mismatch for {name}")
        available[name] = actual
    return available


def previous(build_dir):
    path = build_dir / "sources.json"
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if document.get("format") != FORMAT:
        return {}
    return {face["file"]: face for face in document.get("faces", [])}


def reuse(target, recorded, source_digest):
    return (
        recorded is not None
        and recorded.get("source_sha256") == source_digest
        and target.is_file()
        and digest(target) == recorded.get("sha256")
    )


def assemble(entry, source_dir, build_dir, faces, force):
    name, source_digest = entry
    target = build_dir / name
    if not force and reuse(target, faces.get(name), source_digest):
        return faces[name]
    shutil.copyfile(source_dir / name, target)
    return {
        "file": name,
        "source": name,
        "source_sha256": source_digest,
        "derivative": None,
        "sha256": digest(target),
    }


def license_file(entry, source_dir, build_dir):
    name, source_digest = entry
    target = build_dir / name
    if not (target.is_file() and digest(target) == source_digest):
        shutil.copyfile(source_dir / name, target)
    return {"file": name, "source_sha256": source_digest, "sha256": digest(target)}


def kai(scripts, source_dir, build_dir, values, source_digest, faces, force):
    release = values["KAI_RELEASE"]
    target = build_dir / KAI["file"]
    if not force and reuse(target, faces.get(KAI["file"]), source_digest):
        return faces[KAI["file"]]
    subprocess.run(
        [
            sys.executable,
            str(scripts / "ttf-to-cff.py"),
            str(source_dir / values["KAI_ASSET"]),
            str(target),
            "--ps-name",
            KAI["ps_name"],
            "--family",
            KAI["family"],
            "--style",
            KAI["style"],
            "--description",
            f"Derived from LXGW ZhenKai GB {release} (https://github.com/lxgw/LxgwZhenKai); "
            "outlines converted from TrueType to CFF on the integer grid; otherwise unmodified.",
            "--modified",
            KAI["modified"],
        ],
        check=True,
    )
    return {
        "file": KAI["file"],
        "source": values["KAI_ASSET"],
        "source_sha256": source_digest,
        "derivative": {
            "family": KAI["family"],
            "style": KAI["style"],
            "ps_name": KAI["ps_name"],
            "release": release,
            "commit": values["KAI_COMMIT"],
            "license": "OFL-ZhenKai.txt",
            "conversion": "glyf to CFF at the integer grid, hints dropped",
        },
        "sha256": digest(target),
    }


def attribution(values):
    return {
        "noto-cjk": {
            "source": "https://github.com/notofonts/noto-cjk",
            "commits": {"sans": values["NOTO_SANS_COMMIT"], "serif": values["NOTO_SERIF_COMMIT"]},
            "license": "OFL-Noto-CJK.txt",
        },
        "northstar-kai": {
            "derived_from": "LXGW ZhenKai GB",
            "release": values["KAI_RELEASE"],
            "commit": values["KAI_COMMIT"],
            "license": "OFL-ZhenKai.txt",
            "note": (
                "Renamed to Northstar Kai, so the derivative does not carry the source family and "
                "PostScript names; outlines are the source's on the integer grid, also unhinted."
            ),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="directory fetch-cjk.sh wrote")
    parser.add_argument("build", type=Path, help="directory fontpack builds from")
    parser.add_argument("--force", action="store_true", help="rebuild every face")
    args = parser.parse_args()
    import fontTools

    if fontTools.version != FONTTOOLS_VERSION:
        raise SystemExit(f"fonttools {FONTTOOLS_VERSION} is required, found {fontTools.version}")
    scripts = Path(__file__).resolve().parent
    values = pins(scripts)
    entries = lock(scripts)
    available = sources(entries, args.source)
    args.build.mkdir(parents=True, exist_ok=True)
    faces = previous(args.build)
    built = [
        assemble(entry, args.source, args.build, faces, args.force)
        for entry in entries
        if not entry[0].endswith(".txt") and entry[0] != values["KAI_ASSET"]
    ]
    built.append(
        kai(
            scripts,
            args.source,
            args.build,
            values,
            available[values["KAI_ASSET"]],
            faces,
            args.force,
        )
    )
    licenses = [
        license_file(entry, args.source, args.build)
        for entry in entries
        if entry[0].endswith(".txt")
    ]
    if {entry["file"] for entry in licenses} != set(LICENSES):
        raise SystemExit("both pinned licence texts are required")
    built.sort(key=lambda face: face["file"])
    expected = {face["file"] for face in built}
    for stale in [*args.build.glob("*.otf"), *args.build.glob("*.ttf")]:
        if stale.name not in expected:
            stale.unlink()
    document = {
        "format": FORMAT,
        "lock": "cjk-sources.sha256",
        "pins": "cjk-sources.env",
        "attribution": attribution(values),
        "licenses": licenses,
        "faces": built,
    }
    (args.build / "sources.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    total = sum((args.build / face["file"]).stat().st_size for face in built)
    print(f"{len(built)} CJK faces, {total} bytes, in {args.build}")


if __name__ == "__main__":
    main()
