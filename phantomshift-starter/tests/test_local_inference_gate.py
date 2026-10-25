import unittest

from phantomshift.inference_gate import check_inference_config, is_loopback_host

LOCAL = {"llm": {"base_url": "http://127.0.0.1:8000/v1", "provider": "vllm", "model": "local-model"}}


def codes(res):
    return {v["code"] for v in res["violations"]}


class CompetitionModeTests(unittest.TestCase):
    def check(self, cfg, env=None):
        return check_inference_config(cfg, "competition", env)

    def test_loopback_local_config_passes(self):
        for cfg in (LOCAL,
                    {"base_url": "http://localhost:11434/v1", "provider": "ollama"},
                    {"llm": {"base_url": "http://[::1]:8000/v1", "provider": "openai-compatible"}},
                    {"llm": {"base_url": "http://127.0.0.1:8000/v1"},
                     "embedding": {"base_url": "http://127.0.0.2:8001"}}):
            r = self.check(cfg, {"PATH": "/usr/bin"})
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["violations"], [])

    def test_remote_urls_rejected(self):
        for url in ("https://api.openai.com/v1", "https://integrate.api.nvidia.com/v1", "http://10.0.0.5:8000/v1",
                    "http://0.0.0.0:8000", "http://127.0.0.1.evil.com/v1", "http://localhost.evil.com",
                    "http://2130706433/v1", "api.anthropic.com"):
            r = self.check({"llm": {"base_url": url, "provider": "vllm"}})
            self.assertFalse(r["ok"], url)
            self.assertIn("remote_endpoint", codes(r), url)

    def test_url_tricks_rejected(self):
        for url in ("http://127.0.0.1@evil.com/v1", "http://user:pw@127.0.0.1/v1", " http://127.0.0.1/v1",
                    "http://127.0.0.1:notaport/v1", "ftp://127.0.0.1/x", "file:///etc/passwd", "http:///v1", ""):
            r = self.check({"llm": {"base_url": url}})
            self.assertFalse(r["ok"], repr(url))

    def test_remote_auxiliary_endpoints_rejected_and_attributed(self):
        for comp, key in (("embedding", "embedding"), ("rerank", "reranker"), ("ocr", "ocr"), ("moderation", "moderation")):
            cfg = {**LOCAL, key: {"base_url": "https://api.example-hosted.com/v1"}}
            r = self.check(cfg)
            self.assertFalse(r["ok"], comp)
            self.assertTrue(any(e["component"] == comp and e["host"] == "api.example-hosted.com" for e in r["endpoints"]), comp)

    def test_list_of_endpoints_each_checked(self):
        self.assertTrue(self.check({"llm": {"base_url": ["http://127.0.0.1:1", "http://localhost:2"]}})["ok"])
        self.assertFalse(self.check({"llm": {"base_url": ["http://127.0.0.1:1", "https://remote.example"]}})["ok"])

    def test_endpoint_hidden_under_unexpected_key_is_still_found(self):
        r = self.check({**LOCAL, "extras": [{"note": "https://hosted.example.com/v1"}]})
        self.assertIn("remote_endpoint", codes(r))

    def test_remote_api_keys_in_env_rejected_without_echoing_value(self):
        for name in ("REMOTE_LLM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "NVIDIA_API_KEY",
                     "GEMINI_API_KEY", "OPENROUTER_API_KEY", "NVIDIA_BUILD_TOKEN"):
            r = self.check(LOCAL, {name: "sk-secret-value-123"})
            self.assertFalse(r["ok"], name)
            self.assertIn("remote_api_key", codes(r))
            self.assertNotIn("sk-secret-value-123", repr(r))

    def test_empty_key_value_is_not_a_violation_and_env_not_read_implicitly(self):
        import os
        old = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "sk-in-real-env"
        try:
            self.assertTrue(self.check(LOCAL)["ok"])           # no env passed: real env ignored
            self.assertTrue(self.check(LOCAL, {"OPENAI_API_KEY": ""})["ok"])
        finally:
            if old is None:
                del os.environ["OPENAI_API_KEY"]
            else:
                os.environ["OPENAI_API_KEY"] = old

    def test_env_inside_config_is_also_checked(self):
        r = self.check({**LOCAL, "env": {"ANTHROPIC_API_KEY": "x"}})
        self.assertIn("remote_api_key", codes(r))

    def test_env_base_url_override_must_be_loopback(self):
        r = self.check(LOCAL, {"OPENAI_BASE_URL": "https://api.openai.com/v1"})
        self.assertIn("remote_endpoint", codes(r))
        self.assertTrue(self.check(LOCAL, {"OPENAI_BASE_URL": "http://127.0.0.1:8000/v1"})["ok"])

    def test_hosted_provider_names_rejected(self):
        for prov in ("build", "build.nvidia.com", "openrouter", "OpenAI", "anthropic", "gemini", "google-vertex", "azure-openai"):
            r = self.check({"llm": {"base_url": "http://127.0.0.1:8000/v1", "provider": prov}})
            self.assertFalse(r["ok"], prov)
            self.assertIn("hosted_provider", codes(r))

    def test_unknown_provider_rejected_in_competition(self):
        r = self.check({"llm": {"base_url": "http://127.0.0.1:8000/v1", "provider": "mystery-cloud"}})
        self.assertIn("unknown_provider", codes(r))

    def test_open_weight_model_id_with_vendor_prefix_is_not_a_provider(self):
        r = self.check({"llm": {"base_url": "http://127.0.0.1:8000/v1", "provider": "vllm", "model": "openai/gpt-oss-20b"}})
        self.assertTrue(r["ok"], r)


class MalformedAndPrepTests(unittest.TestCase):
    def test_malformed_configs_rejected_in_both_modes(self):
        bad = [None, "http://127.0.0.1", 42, [], {}, {"llm": None}, {"llm": {"base_url": 8000}},
               {"llm": {"base_url": {"a": 1}}}, {"llm": {"provider": ""}},
               {"llm": {"provider": 7, "base_url": "http://127.0.0.1"}}, {1: {"base_url": "http://127.0.0.1"}},
               {"model": "only-a-model-name"}]
        for mode in ("prep", "competition"):
            for cfg in bad:
                r = check_inference_config(cfg, mode)
                self.assertFalse(r["ok"], (mode, cfg))
                self.assertTrue(r["violations"])

    def test_bad_mode_and_bad_env_rejected(self):
        for mode in ("", "PREP", None, "demo"):
            self.assertFalse(check_inference_config(LOCAL, mode)["ok"], mode)
        self.assertFalse(check_inference_config(LOCAL, "competition", ["not", "a", "mapping"])["ok"])
        self.assertFalse(check_inference_config(LOCAL, "competition", {"OPENAI_API_KEY": 5})["ok"])

    def test_too_deep_or_huge_config_rejected(self):
        deep = cur = {}
        for _ in range(20):
            cur["x"] = {}
            cur = cur["x"]
        self.assertFalse(check_inference_config({**LOCAL, "deep": deep}, "prep")["ok"])
        self.assertFalse(check_inference_config({**LOCAL, "big": list(range(5000))}, "competition")["ok"])

    def test_prep_allows_loopback(self):
        r = check_inference_config(LOCAL, "prep", {})
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["violations"], r["warnings"]), ([], []))

    def test_prep_rejects_non_loopback_url(self):
        r = check_inference_config({"llm": {"base_url": "https://api.openai.com/v1"}}, "prep")
        self.assertFalse(r["ok"])
        self.assertIn("remote_endpoint", codes(r))

    def test_prep_warns_on_keys_and_hosted_provider_names(self):
        cfg = {"llm": {"base_url": "http://127.0.0.1:8000/v1", "provider": "openrouter"}}
        r = check_inference_config(cfg, "prep", {"OPENAI_API_KEY": "sk-x", "SOME_OTHER_API_KEY": "y"})
        self.assertTrue(r["ok"], r)
        wc = {w["code"] for w in r["warnings"]}
        self.assertTrue({"remote_api_key", "hosted_provider", "unrecognised_api_key"} <= wc, wc)
        self.assertNotIn("sk-x", repr(r))

    def test_competition_only_warns_on_unrecognised_generic_key(self):
        r = check_inference_config(LOCAL, "competition", {"WEATHER_API_KEY": "y"})
        self.assertTrue(r["ok"])
        self.assertEqual(r["warnings"][0]["code"], "unrecognised_api_key")

    def test_loopback_helper(self):
        self.assertTrue(all(is_loopback_host(h) for h in ("127.0.0.1", "localhost", "::1", "127.1.2.3")))
        self.assertFalse(any(is_loopback_host(h) for h in ("0.0.0.0", "10.0.0.1", "example.com", "")))


if __name__ == "__main__":
    unittest.main()
