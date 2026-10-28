import json

from models.providers.fake import FakeProvider


def test_fake_provider_returns_a_generic_plan():
    provider = FakeProvider()
    response = provider.generate(
        "You are a structured planning component for an AI agent.\n"
        "User request:\nExplain the deployment process.\n"
        "Previous conversation context:\nNo previous conversation context."
    )

    payload = json.loads(response)
    assert payload["tasks"][0]["capability"] == "model"
    assert payload["tasks"][0]["input"]["query"] == "Explain the deployment process."


def test_fake_provider_returns_delegation_json():
    payload = json.loads(
        FakeProvider().generate("Propose a delegation plan in JSON.")
    )

    assert payload["delegations"]
    assert payload["delegations"][0]["agent"] == "research"


def test_fake_provider_returns_intent_json():
    payload = json.loads(
        FakeProvider().generate(
            "Classify the user request into exactly one intent: retrieval, tool, or general. "
            "Return only JSON with intent, confidence, and entities."
        )
    )

    assert payload == {
        "intent": "general",
        "confidence": 1.0,
        "entities": {},
    }


def test_fake_provider_returns_deterministic_plain_text_for_ordinary_prompts():
    provider = FakeProvider()

    first = provider.generate("Give a concise greeting.")
    second = provider.generate("Give a concise greeting.")

    assert first == second
    assert first
    assert first.startswith("FAKE_RESPONSE:")
