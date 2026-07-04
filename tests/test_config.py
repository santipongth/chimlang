from core.config import Settings


def test_defaults_are_safe():
    s = Settings(_env_file=None)
    assert s.run_budget_usd_cap == 5.0
    assert s.default_seed == 42
    # governance flags ต้องเปิดโดย default (ค่า default ปลอดภัย)
    assert s.pii_detector_enabled is True
    assert s.watermark_enabled is True


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("RUN_BUDGET_USD_CAP", "2.5")
    monkeypatch.setenv("LLM_MODEL_CROWD", "vendor/model-x")
    monkeypatch.setenv("PII_DETECTOR_ENABLED", "true")
    s = Settings(_env_file=None)
    assert s.run_budget_usd_cap == 2.5
    assert s.llm_model_crowd == "vendor/model-x"
