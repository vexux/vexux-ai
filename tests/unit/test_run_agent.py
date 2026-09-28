import logging
import time
from types import SimpleNamespace
from io import StringIO

from scripts.manual import run_agent


class _Route:
    selections = ()


class _Agent:
    def __init__(self, result=None, error=None):
        self.resource_router = self
        self.result = result
        self.error = error
        self.run_kwargs = []

    def route(self, _query):
        return _Route()

    def run(self, _query, **_kwargs):
        self.run_kwargs.append(_kwargs)
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


def test_interactive_runner_does_not_print_agent_none_for_terminal_failure(
    monkeypatch, capsys
):
    class ProgressFailingAgent(_Agent):
        progress_reporter = type("Reporter", (), {"callback": None})()

        def run(self, _query, **kwargs):
            from types import SimpleNamespace

            self.run_kwargs.append(kwargs)
            for event_type, phase, status in (
                ("planning_started", "planning", "started"),
                ("planning_completed", "planning", "completed"),
                ("execution_started", "execution", "started"),
                ("execution_progress", "execution", "failed"),
                ("execution_completed", "execution", "failed"),
            ):
                self.progress_reporter.callback(SimpleNamespace(
                    event_type=event_type,
                    phase=phase,
                    message="",
                    resource="fraud_graph" if status == "failed" else None,
                    status=status,
                    duration_ms=0,
                ))
            return type(
                "FailedResult",
                (),
                {
                    "output": None,
                    "error": "Unauthorized access to knowledge_graph: fraud_graph",
                    "trace": (),
                    "success": False,
                },
            )()

    output = _run_interactive(
        monkeypatch,
        capsys,
        ProgressFailingAgent(),
    )

    assert "x Executing" in output
    assert "Agent:\nNone" not in output
    assert "Unauthorized access to knowledge_graph: fraud_graph" in output
    assert "Exiting..." in output


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


def test_interactive_runner_rejects_unknown_actor(monkeypatch, capsys):
    monkeypatch.setattr(run_agent, "create_real_agent", lambda: _Agent(result=_Result()))
    inputs = iter(("/actor investigater", "question", "exit"))
    monkeypatch.setattr("builtins.input", lambda _prompt: next(inputs))

    output = run_agent.main()

    assert "Unknown actor 'investigater'" in capsys.readouterr().out


def test_interactive_runner_uses_least_privileged_default_actor(monkeypatch, capsys):
    agent = _Agent(result=_Result())
    monkeypatch.setattr(run_agent, "create_real_agent", lambda: agent)
    inputs = iter(("question", "exit"))
    monkeypatch.setattr("builtins.input", lambda _prompt: next(inputs))

    run_agent.main()

    assert agent.run_kwargs[0]["user_id"] == "support_user"


def test_progress_renderer_displays_runtime_resource_data(capsys):
    run_agent._render_progress_event(SimpleNamespace(
        event_type="execution_progress",
        phase="execution",
        message="Resource complete.",
        resource="registered_source",
        status="completed",
        task_id="task-1",
    ))

    assert "    + registered_source" in capsys.readouterr().out


def test_terminal_progress_shows_only_minimal_lifecycle(capsys):
    renderer = run_agent.TerminalProgressRenderer()
    for event_type, phase, duration in (
        ("authorization_started", "authorization", None),
        ("authorization_completed", "authorization", None),
        ("planning_started", "planning", None),
        ("planning_completed", "planning", 1200),
        ("execution_started", "execution", None),
        ("execution_progress", "execution", None),
        ("execution_completed", "execution", 500),
        ("response_started", "response", None),
        ("response_progress", "response", None),
        ("response_completed", "response", 30),
    ):
        renderer.render(SimpleNamespace(
            event_type=event_type,
            phase=phase,
            message=(
                "Generating response..."
                if event_type == "response_progress"
                else "Internal authorization detail."
            ),
            resource="customer_graph" if event_type == "execution_progress" else None,
            status="started" if event_type == "response_progress" else "completed" if event_type in {
                "planning_completed", "execution_progress", "execution_completed",
                "response_completed",
            } else "started",
            task_id="task-1",
            duration_ms=duration,
        ))

    output = capsys.readouterr().out
    assert "> Planning" in output
    assert "+ Planning" in output
    assert "> Executing" in output
    assert "+ Executing" in output
    assert "> Responding" in output
    assert "+ Responding" in output
    assert "generating response..." in output
    assert "[OK]" not in output
    assert "customer_graph" in output
    assert "Authorization" not in output
    assert "Internal authorization detail" not in output
    assert output.count("customer_graph") == 1


def test_terminal_progress_timer_uses_injected_monotonic_clock():
    class FakeClock:
        now = 10.0

        def __call__(self):
            return self.now

    class TTYBuffer(StringIO):
        def isatty(self):
            return True

    clock = FakeClock()
    output = TTYBuffer()
    renderer = run_agent.TerminalProgressRenderer(
        output=output,
        clock=clock,
        tick_interval=0.01,
    )
    renderer.render(SimpleNamespace(
        event_type="planning_started",
        phase="planning",
        message="",
        resource=None,
        status="started",
        duration_ms=None,
    ))
    clock.now = 14.21
    renderer._active["planning"]["stop"].wait(0.03)
    renderer.render(SimpleNamespace(
        event_type="planning_completed",
        phase="planning",
        message="",
        resource=None,
        status="completed",
        duration_ms=None,
    ))

    assert "› Planning" in output.getvalue()
    assert "4.21s" in output.getvalue()
    assert "✓ Planning" in output.getvalue()


def test_tty_completion_overwrites_long_active_line_without_stale_timing():
    class TTYBuffer(StringIO):
        def isatty(self):
            return True

    output = TTYBuffer()
    renderer = run_agent.TerminalProgressRenderer(
        output=output,
        tick_interval=10,
    )
    renderer.render(SimpleNamespace(
        event_type="response_started",
        phase="response",
        message="",
        resource=None,
        status="started",
        duration_ms=None,
    ))
    renderer.render(SimpleNamespace(
        event_type="response_progress",
        phase="response",
        message="Generating response...",
        resource=None,
        status="started",
        duration_ms=None,
    ))
    renderer.render(SimpleNamespace(
        event_type="response_completed",
        phase="response",
        message="Response ready.",
        resource=None,
        status="completed",
        duration_ms=20,
    ))

    final_line = output.getvalue().split("\r")[-1].strip()
    assert final_line == "✓ Responding     0.02s"
    assert final_line.count("0.02s") == 1
    assert "0s" not in final_line


def test_failed_execution_stops_timer_and_never_marks_resource_successful():
    class FakeClock:
        now = 10.0

        def __call__(self):
            return self.now

    class TTYBuffer(StringIO):
        def isatty(self):
            return True

    clock = FakeClock()
    output = TTYBuffer()
    renderer = run_agent.TerminalProgressRenderer(
        output=output,
        clock=clock,
        tick_interval=0.01,
    )
    renderer.render(SimpleNamespace(
        event_type="execution_started",
        phase="execution",
        message="",
        resource=None,
        status="started",
        duration_ms=None,
    ))
    clock.now = 10.35
    renderer.render(SimpleNamespace(
        event_type="execution_progress",
        phase="execution",
        message="Task execution completed.",
        resource="fraud_graph",
        status="failed",
        duration_ms=350,
    ))
    renderer.render(SimpleNamespace(
        event_type="execution_completed",
        phase="execution",
        message="Task execution completed.",
        resource="fraud_graph",
        status="failed",
        duration_ms=350,
    ))
    after_failure = output.getvalue()
    clock.now = 15.0
    time.sleep(0.03)

    assert renderer._active == {}
    assert "✗ Executing" in after_failure
    assert "fraud_graph" not in after_failure
    assert after_failure.count("✗ Executing") == 1
    assert output.getvalue() == after_failure
