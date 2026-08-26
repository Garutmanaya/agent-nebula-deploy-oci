import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "image_pipeline.py"
spec = importlib.util.spec_from_file_location("image_pipeline", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class ImagePipelineTests(unittest.TestCase):
    def test_image_ref(self):
        self.assertEqual(
            module.image_ref("ghcr.io", "example", "nebula-policy", "v1-arm64"),
            "ghcr.io/example/nebula-policy:v1-arm64",
        )

    def test_policy_manifest_is_enabled(self):
        defaults, specs = module.load_manifest(Path(__file__).parents[1] / "config" / "images.json")
        policy = next(item for item in specs if item.name == "policy")
        self.assertTrue(policy.enabled)
        self.assertEqual(defaults["platforms"], ["linux/arm64"])
        self.assertIn("agent_nebula_policy_sdk", policy.build_contexts)

    def test_all_selects_all_enabled_images(self):
        specs = [
            module.ImageSpec("a", "a", "a", "Dockerfile", enabled=True),
            module.ImageSpec("b", "b", "b", "Dockerfile", enabled=False),
            module.ImageSpec("c", "c", "c", "Dockerfile", enabled=True),
        ]
        self.assertEqual([item.name for item in module.select(specs, ["all"])], ["a", "c"])

    def test_all_cannot_be_combined_with_names(self):
        specs = [module.ImageSpec("a", "a", "a", "Dockerfile")]
        with self.assertRaises(ValueError):
            module.select(specs, ["all", "a"])

    def test_release_tags(self):
        cfg = module.RegistryConfig(
            provider="ghcr",
            host="ghcr.io",
            namespace="example",
            architecture="arm64",
            tag_templates=("{release}-{arch}", "latest-{arch}"),
        )
        self.assertEqual(module.release_tags(cfg, "0.5.0"), ["0.5.0-arm64", "latest-arm64"])

    def test_registry_config(self):
        payload = {
            "schema_version": 1,
            "registry": {"provider": "ghcr", "host": "ghcr.io", "namespace": "example"},
            "release": {"architecture": "arm64", "tag_templates": ["{release}-{arch}"]},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            cfg = module.load_registry(path)
        self.assertEqual(cfg.host, "ghcr.io")
        self.assertEqual(cfg.namespace, "example")

    def test_multi_platform_load_is_rejected(self):
        spec_obj = module.ImageSpec(name="x", repository="x", image="x", dockerfile="Dockerfile")
        with self.assertRaises(ValueError):
            module.build_command(
                spec=spec_obj,
                repo=Path("/tmp/x"),
                images=["x:dev-arm64"],
                platforms=["linux/amd64", "linux/arm64"],
                push=False,
                load=True,
            )


if __name__ == "__main__":
    unittest.main()
