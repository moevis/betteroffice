#!/usr/bin/env python3
"""Publish a versioned font package, then verify its CDN resources."""
import argparse
import concurrent.futures
import hashlib
import json
import mimetypes
import os
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

CACHE_CONTROL = "public,max-age=31536000,immutable"
IMMUTABLE_MAX_AGE = 31536000


def cache_problems(value):
    """Reasons an object misses the immutable font contract, empty when it is safe to cache."""
    if value is None:
        return ["no Cache-Control header"]
    directives = {}
    for part in value.split(","):
        directive, _, argument = part.partition("=")
        directive = directive.strip().lower()
        if directive:
            directives[directive] = argument.strip().strip('"')
    problems = [f"{name} forbids reusable caching" for name in ("no-store", "no-cache", "private")
                if name in directives]
    problems.extend(f"missing {name}" for name in ("public", "immutable") if name not in directives)
    if "max-age" not in directives:
        problems.append("missing max-age")
    else:
        try:
            seconds = int(directives["max-age"])
        except ValueError:
            problems.append(f"invalid max-age {directives['max-age']}")
        else:
            if seconds < IMMUTABLE_MAX_AGE:
                problems.append(f"max-age {seconds} is shorter than {IMMUTABLE_MAX_AGE}")
    return problems


def require_cache(value, subject):
    problems = cache_problems(value)
    if problems:
        raise ValueError(f"font resource is not immutably cacheable: {subject}: {'; '.join(problems)}")


def collect(package):
    package = package.resolve()
    metadata = json.loads((package / "package.json").read_text())
    short = metadata["name"].split("/")[-1]
    version = metadata["version"]
    assets = package / "assets"
    manifest_name = "manifest.json" if (assets / "manifest.json").is_file() else "base-latin.json"
    manifest = json.loads((assets / manifest_name).read_text())
    if manifest_name == "manifest.json" and manifest["version"] != version:
        raise ValueError("font package and manifest versions differ")
    names = {manifest_name}
    for face in manifest["faces"]:
        names.add(face["file"])
        if face.get("dict"):
            names.add(face["dict"])
        if face.get("slices"):
            index_name = face["slices"]["index"]
            index_bytes = inside(assets, index_name).read_bytes()
            if hashlib.sha256(index_bytes).hexdigest() != face["slices"]["indexSha256"]:
                raise ValueError(f"slice index hash mismatch: {index_name}")
            names.add(index_name)
            index = json.loads(index_bytes)
            names.update(part["file"] for part in [index["skeleton"], index["core"], *index["chunks"]])
    files = {}
    for name in sorted(names):
        path = inside(assets, name)
        files[f"assets/{name}"] = path
    if manifest_name == "base-latin.json":
        files["dist/decoder/fontpack.wasm"] = inside(package, "dist/decoder/fontpack.wasm")
    for path in sorted((package / "LICENSES").rglob("*")):
        if path.is_file():
            files[path.relative_to(package).as_posix()] = path
    files["LICENSE"] = package / "LICENSE"
    return f"{short}/{version}", files, f"assets/{manifest_name}"


def inside(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"missing or invalid font resource: {name}")
    return path


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"missing environment variable: {name}")
    return value


def publish(prefix, files, workers, manifest_name):
    import tos
    client = tos.TosClientV2(required("TOS_ACCESS_KEY"), required("TOS_SECRET_KEY"),
                             required("TOS_ENDPOINT"), required("TOS_REGION"))
    bucket = required("TOS_BUCKET")

    def upload(item):
        name, path = item
        key = f"{prefix}/{name}"
        sha = digest(path)
        size = path.stat().st_size
        try:
            with path.open("rb") as content:
                client.put_object(bucket, key, content=content, content_length=size,
                                  content_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
                                  cache_control=CACHE_CONTROL,
                                  meta={"sha256": sha}, forbid_overwrite=True)
        except tos.exceptions.TosServerError as error:
            if error.status_code != 409:
                raise
            existing = client.head_object(bucket, key)
            if existing.content_length != size or (existing.meta or {}).get("sha256") != sha:
                raise ValueError(f"refusing to overwrite different font resource: {key}") from error
            try:
                require_cache(getattr(existing, "cache_control", None), key)
            except ValueError as invalid:
                raise ValueError(f"existing font resource keeps stale cache metadata: {invalid}") from error
        return key

    ordered = sorted(files.items(), key=lambda item: item[0].endswith(".json"))
    binaries = [item for item in ordered if not item[0].endswith(".json")]
    indexes = [item for item in ordered if item[0].endswith(".json") and item[0] != manifest_name]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for group in [binaries, indexes, [(manifest_name, files[manifest_name])]]:
            list(pool.map(upload, group))


def verify(prefix, files, cdn, origin, workers):
    if urlsplit(cdn).scheme != "https":
        raise ValueError("CDN base must use HTTPS")

    def check(item):
        name, path = item
        url = f"{cdn.rstrip('/')}/{quote(prefix + '/' + name, safe='/')}"
        request = Request(url, headers={"Origin": origin, "Accept-Encoding": "identity"})
        with urlopen(request, timeout=45) as response:
            # A fixed single-origin CDN policy answers with the consumer origin and no Vary,
            # so only an unrelated Access-Control-Allow-Origin is refused here.
            if response.headers.get("Access-Control-Allow-Origin") not in ("*", origin):
                raise ValueError(f"font resource has no matching CORS origin: {url}")
            require_cache(response.headers.get("Cache-Control"), url)
            expected = path.stat().st_size
            hasher = hashlib.sha256()
            received = 0
            while block := response.read(1 << 20):
                hasher.update(block)
                received += len(block)
        if received != expected:
            raise ValueError(f"CDN resource length mismatch: {url}: {received} != {expected}")
        if hasher.hexdigest() != digest(path):
            raise ValueError(f"CDN resource hash mismatch: {url}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(check, files.items()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--cdn", default="https://static-northstar.stepfun.com")
    parser.add_argument("--origin", default="https://northstar.c.stepfun-inc.net")
    parser.add_argument("--workers", type=int, default=8, choices=range(1, 17))
    args = parser.parse_args()
    prefix, files, manifest_name = collect(args.package)
    print(f"{prefix}: {len(files)} resources, {sum(p.stat().st_size for p in files.values())} bytes")
    if args.publish:
        publish(prefix, files, args.workers, manifest_name)
    if args.verify:
        verify(prefix, files, args.cdn, args.origin, args.workers)
    print("Font publication checks passed" if args.verify else "Font resource preparation completed")


if __name__ == "__main__":
    main()
