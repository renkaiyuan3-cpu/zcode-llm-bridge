#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from lib_zcode_providers import (  # noqa: E402
    anthropic_reasoning_spec,
    apply_reasoning,
    ensure_provider,
    load_cfg,
    openai_reasoning_spec,
    save_cfg,
)


class ReasoningSpecTests(unittest.TestCase):
    def test_anthropic_high_budget(self):
        spec = anthropic_reasoning_spec()
        value = spec["levels"]["high"]["anthropic"]["set"][0]["value"]
        self.assertEqual(value["type"], "enabled")
        self.assertEqual(value["budgetTokens"], 60000)
        self.assertNotIn("xhigh", spec["levels"])

    def test_anthropic_xhigh(self):
        spec = anthropic_reasoning_spec(include_xhigh=True)
        self.assertIn("xhigh", spec["levels"])
        self.assertEqual(
            spec["levels"]["xhigh"]["anthropic"]["set"][0]["value"]["budgetTokens"],
            65535,
        )

    def test_openai_off_maps_to_none(self):
        spec = openai_reasoning_spec(["off", "low"])
        mapped = spec["levels"]["off"]["openai-compatible"]["set"][0]["value"]
        self.assertEqual(mapped, "none")
        self.assertEqual(
            spec["levels"]["low"]["openai-compatible"]["set"][0]["value"],
            "low",
        )


class ProviderWriteTests(unittest.TestCase):
    def test_ensure_provider_rotates_api_key(self):
        cfg = {}
        template = {
            "name": "Demo",
            "kind": "anthropic",
            "options": {"apiKey": "old", "baseURL": "http://127.0.0.1:9"},
        }
        provider, created = ensure_provider(cfg, "demo", template)
        self.assertTrue(created)
        template["options"]["apiKey"] = "new"
        provider, changed = ensure_provider(cfg, "demo", template)
        self.assertTrue(changed)
        self.assertEqual(provider["options"]["apiKey"], "new")
        _, changed_again = ensure_provider(cfg, "demo", template)
        self.assertFalse(changed_again)

    def test_apply_reasoning_idempotent(self):
        model = {}
        spec = anthropic_reasoning_spec()
        self.assertTrue(apply_reasoning(model, spec))
        self.assertFalse(apply_reasoning(model, spec))
        self.assertEqual(model["reasoningSpec"], spec)
        self.assertEqual(model["zcode"]["reasoning"], spec)

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            save_cfg({"hello": "世界"}, path)
            self.assertEqual(load_cfg(path), {"hello": "世界"})


if __name__ == "__main__":
    unittest.main()
