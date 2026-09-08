import logging

from scripts.manual import run_agent


class _Route:
    selections = ()


class _Agent:
    def __init__(self, result=None, error=None):
        self.resource_router = self
        self.result = result
        self.error = error

    def route(self, _query):
        return _Route()

    def run(self, _query, **_kwargs):
        if self.error:
            raise self.error
        return self.result


class _Result:
    output = "normal response"
    error = None
    trace = ()
    success = True


def _run_interactive(monkeypatch, capsys, agent, configured_provider="mistral"):
    monkeypatch.setattr(run_agent, "create_real_agent", lambda: agent)
    monkeypatch.setattr(
        run_agent,
        "get_config",
        lambda: type("Config", (), {"model_provider": configured_provider})(),
    )
    inputs = iter(("question", "exit"))
    monkeypatch.setattr("builtins.input", lambda _prompt: next(inputs))
    run_agent.main()
    return capsys.readouterr().out


def test_interactive_runner_preserves_successful_response(monkeypatch, capsys):
    output = _run_interactive(monkeypatch, capsys, _Agent(result=_Result()))

    assert "normal response" in output
    assert "could not complete" not in output


def test_interactive_runner_handles_provider_runtime_error(monkeypatch, capsys, caplog):
    error = RuntimeError("Mistral API generation failed.")

    with caplog.at_level(logging.ERROR, logger=run_agent.__name__):
        output = _run_interactive(monkeypatch, capsys, _Agent(error=error))

    assert "configured model provider 'mistral' could not complete the request" in output
    assert "Traceback" not in output
    assert "Interactive model provider request failed." in caplog.text


def test_interactive_runner_handles_rate_limit_error(monkeypatch, capsys):
    error = RuntimeError(
        "Mistral API generation failed."
    )
    error.__cause__ = RuntimeError("HTTP 429 rate_limited")

    output = _run_interactive(monkeypatch, capsys, _Agent(error=error))

    assert "temporarily unavailable or rate limited" in output
    assert "Traceback" not in output
