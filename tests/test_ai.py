import json
import pytest
from ameblo_studio import ai
from ameblo_studio.content import demo_copy
from ameblo_studio.models import Brief, Settings
from dataclasses import asdict


@pytest.mark.parametrize("provider", ["OpenAI", "Gemini"])
def test_provider_payload_and_result(provider, monkeypatch):
    payloads = []
    def fake(url, headers, payload):
        payloads.append((url, headers, payload))
        raw = json.dumps(asdict(demo_copy()))
        if provider == "OpenAI":
            return {"status": "completed", "output": [{"content": [{"type": "output_text", "text": raw}]}]}
        return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": raw}]}}]}
    monkeypatch.setattr(ai, "post_json", fake)
    settings = Settings(provider=provider, openai_key="test", gemini_key="test")
    result = ai.generate(Brief("가을 소개", event="原文 990円"), settings)
    assert result == demo_copy()
    assert "990" not in json.dumps(payloads)
    if provider == "OpenAI":
        assert payloads[0][2]["store"] is False
    else:
        assert "key=" not in payloads[0][0]


def test_refusal_is_not_valid_content(monkeypatch):
    monkeypatch.setattr(ai, "post_json", lambda *a: {"status": "completed", "output": [{"content": [{"type": "refusal", "refusal": "no"}]}]})
    with pytest.raises(ValueError):
        ai.generate(Brief("topic"), Settings(openai_key="test"))


def test_incomplete_response(monkeypatch):
    monkeypatch.setattr(ai, "post_json", lambda *a: {"status": "incomplete"})
    with pytest.raises(ValueError):
        ai.generate(Brief("topic"), Settings(openai_key="test"))
