import os

from core.model_gateway.gateway import ModelGateway


def test_fake_provider_integration():
    os.environ.setdefault("MODEL_PROVIDER", "fake")
    # Import composition to build provider via env
    from core.composition import create_agent
    agent = create_agent()
    # ensure model_gateway is set on planner via agent
    mg = agent.planner.model_gateway
    assert isinstance(mg, ModelGateway)
    out = mg.generate("Please propose delegations")
    assert isinstance(out, str)
    # If the fake provider runs, it should return a string starting with FAKE_RESPONSE or JSON
    assert out.startswith("FAKE_RESPONSE") or out.strip().startswith("{")
