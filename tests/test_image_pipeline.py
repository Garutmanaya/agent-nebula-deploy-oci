import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "image_pipeline.py"
spec = importlib.util.spec_from_file_location("image_pipeline", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
import sys
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class ImagePipelineTests(unittest.TestCase):
    def test_image_ref(self):
        self.assertEqual(
            module.image_ref("iad.ocir.io", "namespace", "nebula-policy", "v1"),
            "iad.ocir.io/namespace/nebula-policy:v1",
        )

    def test_policy_manifest_is_enabled(self):
        defaults, specs = module.load_manifest(Path(__file__).parents[1] / "config" / "images.json")
        policy = next(item for item in specs if item.name == "policy")
        self.assertTrue(policy.enabled)
        self.assertEqual(defaults["platforms"], ["linux/arm64"])
        self.assertIn("agent_nebula_policy_sdk", policy.build_contexts)

    def test_multi_platform_load_is_rejected(self):
        spec_obj = module.ImageSpec(
            name="x", repository="x", image="x", dockerfile="Dockerfile"
        )
        with self.assertRaises(ValueError):
            module.build_command(
                spec=spec_obj,
                repo=Path("/tmp/x"),
                workspace=Path("/tmp"),
                image="x:dev",
                platforms=["linux/amd64", "linux/arm64"],
                push=False,
                load=True,
            )


if __name__ == "__main__":
    unittest.main()
