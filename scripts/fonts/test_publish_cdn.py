"""Checks of publish-cdn.py against mocked CDN and TOS responses (standard library only)."""

import email.message
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).with_name("publish-cdn.py")
SPEC = importlib.util.spec_from_file_location("publish_cdn", SCRIPT)
CDN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CDN)

CACHE = "public,max-age=31536000,immutable"
ORIGIN = "https://northstar.c.stepfun-inc.net"
BASE = "https://cdn.example.test"


class Reply(io.BytesIO):
    """A urlopen result with the headers a CDN returns for a published object."""

    def __init__(self, body, fields):
        super().__init__(body)
        self.headers = email.message.Message()
        for name, value in fields.items():
            self.headers[name] = value

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.close()
        return False


class ResponseChecks(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.body = b"\x28\xb5\x2f\xfd staged latin face"
        self.path = Path(work.name, "face.ttf.zst")
        self.path.write_bytes(self.body)
        self.files = {"assets/face.ttf.zst": self.path}

    def verify(self, cache=CACHE, allow_origin="*", body=None, cdn=BASE):
        fields = {"Access-Control-Allow-Origin": allow_origin}
        if cache is not None:
            fields["Cache-Control"] = cache
        reply = Reply(self.body if body is None else body, fields)
        with mock.patch.object(CDN, "urlopen", return_value=reply) as opener:
            CDN.verify("fonts-latin/0.4.2", self.files, cdn, ORIGIN, 1)
        return opener

    def refused(self, message, **fields):
        with self.assertRaisesRegex(ValueError, message):
            self.verify(**fields)

    def test_immutable_cache_control_is_accepted(self):
        opener = self.verify()
        request = opener.call_args.args[0]
        self.assertTrue(request.full_url.startswith(f"{BASE}/fonts-latin/0.4.2/assets/face.ttf.zst"))
        self.assertEqual(request.get_header("Origin"), ORIGIN)

    def test_a_missing_cache_control_header_is_refused(self):
        self.refused("no Cache-Control header", cache=None)

    def test_directives_that_forbid_reuse_are_refused(self):
        for directive in ("no-store", "no-cache", "private"):
            for cache in (directive, f"public,{directive},max-age=31536000,immutable",
                          f"{CACHE},{directive}"):
                with self.subTest(cache=cache):
                    self.refused(f"{directive} forbids reusable caching", cache=cache)

    def test_a_missing_public_directive_is_refused(self):
        self.refused("missing public", cache="max-age=31536000,immutable")

    def test_a_missing_immutable_directive_is_refused(self):
        self.refused("missing immutable", cache="public,max-age=31536000")

    def test_a_short_or_broken_max_age_is_refused(self):
        for cache, message in (
            ("public,immutable", "missing max-age"),
            ("public,max-age=3600,immutable", "shorter than 31536000"),
            ("public,max-age=31535999,immutable", "shorter than 31536000"),
            ("public,max-age=forever,immutable", "invalid max-age forever"),
        ):
            with self.subTest(cache=cache):
                self.refused(message, cache=cache)

    def test_one_second_longer_max_age_is_accepted(self):
        self.verify(cache="public,max-age=31536001,immutable")

    def test_an_unrelated_cors_origin_is_refused(self):
        self.refused("no matching CORS origin", allow_origin="https://elsewhere.test")

    def test_the_consumer_origin_is_accepted_without_vary(self):
        self.verify(allow_origin=ORIGIN)

    def test_different_bytes_at_the_same_length_are_refused(self):
        self.refused("hash mismatch", body=b"\x00" * len(self.body))

    def test_a_shorter_body_is_refused(self):
        self.refused("length mismatch", body=self.body[:-1])

    def test_a_longer_body_is_refused(self):
        self.refused("length mismatch", body=self.body + b"\x00")

    def test_plain_http_cdn_is_refused(self):
        self.refused("CDN base must use HTTPS", cdn="http://cdn.example.test")


class ServerError(Exception):
    def __init__(self, status_code):
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class ExistingObject:
    def __init__(self, content_length, meta, cache_control):
        self.content_length = content_length
        self.meta = meta
        self.cache_control = cache_control


class ExistingObjects(unittest.TestCase):
    PREFIX = "fonts-latin/0.4.2"

    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.face = Path(work.name, "face.ttf.zst")
        self.face.write_bytes(b"\x28\xb5\x2f\xfd already published face")
        self.manifest = Path(work.name, "manifest.json")
        self.manifest.write_bytes(b'{"faces":[]}')
        self.files = {"assets/face.ttf.zst": self.face, "assets/manifest.json": self.manifest}
        environment = mock.patch.dict(os.environ, {
            "TOS_ACCESS_KEY": "test-access-key",
            "TOS_SECRET_KEY": "test-secret-key",
            "TOS_ENDPOINT": "tos.example.test",
            "TOS_REGION": "test-region",
            "TOS_BUCKET": "test-bucket",
        })
        environment.start()
        self.addCleanup(environment.stop)

    def object_for(self, path, cache_control=CACHE):
        return ExistingObject(path.stat().st_size, {"sha256": CDN.digest(path)}, cache_control)

    def client(self, face=None, manifest=None):
        client = mock.Mock()
        client.put_object.side_effect = ServerError(409)
        objects = {"assets/face.ttf.zst": face or self.object_for(self.face),
                   "assets/manifest.json": manifest or self.object_for(self.manifest)}
        client.head_object.side_effect = lambda bucket, key: objects[key.removeprefix(self.PREFIX + "/")]
        return client

    def execute(self, client):
        tos = types.ModuleType("tos")
        tos.exceptions = types.SimpleNamespace(TosServerError=ServerError)
        tos.TosClientV2 = mock.Mock(return_value=client)
        with mock.patch.dict(sys.modules, {"tos": tos}):
            CDN.publish(self.PREFIX, self.files, 1, "assets/manifest.json")

    def publish(self, face=None, manifest=None):
        client = self.client(face, manifest)
        self.execute(client)
        return client

    @staticmethod
    def face_uploads(client):
        return [call for call in client.put_object.call_args_list
                if call.args[1].endswith("/assets/face.ttf.zst")]

    def test_a_matching_object_with_immutable_cache_is_reused(self):
        client = self.publish()
        client.head_object.assert_any_call("test-bucket", f"{self.PREFIX}/assets/face.ttf.zst")
        self.assertEqual(len(self.face_uploads(client)), 1)
        self.assertEqual(len(client.put_object.call_args_list), 2)

    def test_requests_write_immutable_objects_without_overwrite(self):
        client = self.publish()
        for upload in self.face_uploads(client):
            arguments = upload.kwargs
            self.assertEqual(arguments["cache_control"], CACHE)
            self.assertTrue(arguments["forbid_overwrite"])
            self.assertEqual(arguments["meta"], {"sha256": CDN.digest(self.face)})

    def test_an_existing_object_without_cache_control_is_refused(self):
        with self.assertRaisesRegex(ValueError, "stale cache metadata.*no Cache-Control header"):
            self.publish(self.object_for(self.face, cache_control=None))

    def test_an_existing_object_that_forbids_reuse_is_refused(self):
        for cache_control in ("no-store", "no-cache", f"private,{CACHE}",
                              "public,max-age=60,immutable", "public,immutable"):
            with self.subTest(cache_control=cache_control):
                with self.assertRaisesRegex(ValueError, "stale cache metadata"):
                    self.publish(self.object_for(self.face, cache_control=cache_control))

    def test_an_existing_manifest_with_bad_cache_metadata_is_refused(self):
        with self.assertRaisesRegex(ValueError, "stale cache metadata"):
            self.publish(manifest=self.object_for(self.manifest, cache_control="no-store"))

    def test_a_refused_existing_object_is_never_rewritten(self):
        refused = {
            "no cache-control": self.object_for(self.face, cache_control=None),
            "short max-age": self.object_for(self.face, cache_control="public,max-age=60,immutable"),
            "other length": ExistingObject(self.face.stat().st_size + 1,
                                           {"sha256": CDN.digest(self.face)}, CACHE),
            "other bytes": ExistingObject(self.face.stat().st_size, {"sha256": "0" * 64}, CACHE),
        }
        for reason, existing in refused.items():
            with self.subTest(reason=reason):
                client = self.client(face=existing)
                with self.assertRaises(ValueError):
                    self.execute(client)
                self.assertEqual(len(self.face_uploads(client)), 1)
                client.head_object.assert_any_call("test-bucket", f"{self.PREFIX}/assets/face.ttf.zst")

    def test_an_object_with_different_bytes_is_refused(self):
        with self.assertRaisesRegex(ValueError, "refusing to overwrite different font resource"):
            self.publish(ExistingObject(self.face.stat().st_size, {"sha256": "0" * 64}, CACHE))

    def test_an_object_with_a_missing_hash_is_refused(self):
        with self.assertRaisesRegex(ValueError, "refusing to overwrite different font resource"):
            self.publish(ExistingObject(self.face.stat().st_size, None, CACHE))


class PackageInventory(unittest.TestCase):
    def package(self, name, version, manifest_name, manifest_version, faces=("face.ttf.zst",),
                decoder=False):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        root = Path(work.name)
        (root / "assets").mkdir()
        (root / "LICENSES").mkdir()
        (root / "package.json").write_text(json.dumps({"name": f"@betteroffice/{name}", "version": version}))
        (root / "LICENSE").write_text("license\n")
        (root / "LICENSES/OFL-Noto.txt").write_text("license\n")
        (root / "assets" / manifest_name).write_text(json.dumps({
            "version": manifest_version,
            "faces": [{"file": face, "sha256": "0" * 64} for face in faces],
        }))
        for face in faces:
            (root / "assets" / face).write_bytes(b"face")
        if decoder:
            (root / "dist/decoder").mkdir(parents=True)
            (root / "dist/decoder/fontpack.wasm").write_bytes(b"\x00asm")
        return root

    def test_a_manifest_package_publishes_its_assets_and_licenses(self):
        prefix, files, manifest = CDN.collect(self.package("fonts-intl", "0.4.2", "manifest.json", "0.4.2"))
        self.assertEqual(prefix, "fonts-intl/0.4.2")
        self.assertEqual(manifest, "assets/manifest.json")
        self.assertEqual(sorted(files), ["LICENSE", "LICENSES/OFL-Noto.txt",
                                         "assets/face.ttf.zst", "assets/manifest.json"])

    def test_the_manager_package_reads_base_latin_and_adds_the_decoder(self):
        prefix, files, manifest = CDN.collect(
            self.package("fonts", "0.5.0", "base-latin.json", "1", decoder=True))
        self.assertEqual(prefix, "fonts/0.5.0")
        self.assertEqual(manifest, "assets/base-latin.json")
        self.assertIn("dist/decoder/fontpack.wasm", files)
        self.assertIn("assets/base-latin.json", files)

    def test_a_manager_without_its_decoder_cannot_be_published(self):
        root = self.package("fonts", "0.5.0", "base-latin.json", "1")
        with self.assertRaisesRegex(ValueError, "missing or invalid font resource: dist/decoder/fontpack.wasm"):
            CDN.collect(root)

    def test_a_manifest_version_that_differs_from_the_package_is_refused(self):
        with self.assertRaisesRegex(ValueError, "versions differ"):
            CDN.collect(self.package("fonts-latin", "0.4.2", "manifest.json", "0.4.1"))

    def test_a_sliced_pack_publishes_its_index_and_chunks(self):
        root = self.package("fonts-cjk", "0.5.0", "manifest.json", "0.5.0", decoder=False)
        index = {"skeleton": {"file": "face.skeleton"}, "core": {"file": "face.core"},
                 "chunks": [{"file": "face.c1"}, {"file": "face.c2"}]}
        (root / "assets/face.slices.json").write_text(json.dumps(index))
        manifest_path = root / "assets/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["faces"][0]["slices"] = {
            "index": "face.slices.json",
            "indexSha256": hashlib.sha256((root / "assets/face.slices.json").read_bytes()).hexdigest(),
        }
        manifest_path.write_text(json.dumps(manifest))
        for part in ("face.skeleton", "face.core", "face.c1", "face.c2"):
            (root / "assets" / part).write_bytes(b"part")
        _, files, _ = CDN.collect(root)
        for part in ("face.skeleton", "face.core", "face.c1", "face.c2", "face.slices.json"):
            self.assertIn(f"assets/{part}", files)

    def test_a_slice_index_with_a_stale_hash_is_refused(self):
        root = self.package("fonts-cjk", "0.5.0", "manifest.json", "0.5.0", decoder=False)
        (root / "assets/face.slices.json").write_text(json.dumps(
            {"skeleton": {"file": "face.skeleton"}, "core": {"file": "face.core"}, "chunks": []}))
        manifest_path = root / "assets/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["faces"][0]["slices"] = {"index": "face.slices.json", "indexSha256": "0" * 64}
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "slice index hash mismatch"):
            CDN.collect(root)

    def test_a_face_missing_from_the_package_is_refused(self):
        root = self.package("fonts-latin", "0.4.2", "manifest.json", "0.4.2",
                            faces=("face.ttf.zst", "absent.ttf.zst"))
        (root / "assets/absent.ttf.zst").unlink()
        with self.assertRaisesRegex(ValueError, "missing or invalid font resource"):
            CDN.collect(root)


if __name__ == "__main__":
    unittest.main()
