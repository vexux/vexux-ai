"""Interactive runner for the real local fraud application."""

import logging
import sys
import threading
import time

from apps.fraud.real import create_real_agent
from apps.fraud.identity import DEFAULT_ACTOR, validate_actor
from core.config import get_config, provider_diagnostic
from core.observability_store import get_observability_store


LOGGER = logging.getLogger(__name__)


class TerminalProgressRenderer:
    """Render only lifecycle phases and deduplicated resource milestones."""

    _PHASES = {
        "planning": "Planning",
        "execution": "Executing",
        "response": "Responding",
    }
    _START_EVENTS = {
        "planning_started": "planning",
        "execution_started": "execution",
        "response_started": "response",
    }
    _END_EVENTS = {
        "planning_completed": "planning",
        "response_completed": "response",
    }
    _FAILED_EVENTS = {
        "planning_failed": "planning",
        "workflow_failed": "execution",
    }

    def __init__(
        self,
        output=None,
        clock=time.monotonic,
        tick_interval: float = 0.25,
    ):
        self.output = output or sys.stdout
        self.clock = clock
        self.tick_interval = tick_interval
        self._lock = threading.Lock()
        self._active: dict[str, dict] = {}
        self._resources: set[str] = set()
        self._live_line_width = 0
        self._interactive = bool(
            getattr(self.output, "isatty", lambda: False)()
        )
        self._terminal_phases: set[str] = set()

    @staticmethod
    def _duration_text(duration: float) -> str:
        return f"{max(0.0, duration):.2f}s"

    def _symbol(self, symbol: str, fallback: str) -> str:
        if not self._interactive:
            return fallback
        encoding = getattr(self.output, "encoding", None)
        if not encoding:
            return symbol
        try:
            symbol.encode(encoding)
        except (LookupError, UnicodeEncodeError):
            return fallback
        return symbol

    def _write(self, text: str, *, live: bool = False) -> None:
        with self._lock:
            if live and self._interactive:
                self._live_line_width = max(self._live_line_width, len(text))
                self.output.write("\r" + text.ljust(self._live_line_width))
            else:
                self.output.write(text + "\n")
                self._live_line_width = 0
            self.output.flush()

    def _write_final(self, text: str) -> None:
        with self._lock:
            if self._interactive:
                width = max(self._live_line_width, len(text))
                self.output.write("\r" + text.ljust(width) + "\n")
            else:
                self.output.write(text + "\n")
            self._live_line_width = 0
            self.output.flush()

    def _line(
        self,
        marker: str,
        phase: str,
        duration: float,
        message: str = "",
    ) -> str:
        activity = f" {message}" if message else ""
        return (
            f"{marker} {self._PHASES[phase]:<12}{activity}"
            f"{self._duration_text(duration):>8}"
        )

    def _start(self, phase: str, message: str = "") -> None:
        if phase in self._active:
            return
        self._terminal_phases.discard(phase)
        started = self.clock()
        stop = threading.Event()
        state = {
            "started": started,
            "stop": stop,
            "thread": None,
            "message": message,
        }
        self._active[phase] = state
        self._write(
            self._line(self._symbol("›", ">"), phase, 0.0, message),
            live=True,
        )
        if self._interactive:
            thread = threading.Thread(
                target=self._tick,
                args=(phase, state),
                daemon=True,
            )
            state["thread"] = thread
            thread.start()

    def _tick(self, phase: str, state: dict) -> None:
        stop = state["stop"]
        while not stop.wait(self.tick_interval):
            elapsed = self.clock() - state["started"]
            self._write(
                self._line(
                    self._symbol("›", ">"),
                    phase,
                    elapsed,
                    state["message"],
                ),
                live=True,
            )

    def _finish(self, phase: str, duration_ms: float | None = None) -> None:
        state = self._active.pop(phase, None)
        if state is None:
            return
        state["stop"].set()
        thread = state["thread"]
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(self.tick_interval * 2, 0.1))
        self._terminal_phases.add(phase)
        elapsed = (
            duration_ms / 1000.0
            if duration_ms is not None
            else self.clock() - state["started"]
        )
        self._write_final(
            self._line(self._symbol("✓", "+"), phase, elapsed)
        )

    def _fail(self, phase: str) -> None:
        state = self._active.pop(phase, None)
        if state is None:
            if phase in self._terminal_phases:
                return
            self._terminal_phases.add(phase)
            self._write_final(
                f"{self._symbol('✗', 'x')} {self._PHASES[phase]}"
            )
            return
        state["stop"].set()
        thread = state["thread"]
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(self.tick_interval * 2, 0.1))
        self._terminal_phases.add(phase)
        self._write_final(
            self._line(
                self._symbol("✗", "x"),
                phase,
                self.clock() - state["started"],
            )
        )

    def _resource_completed(self, resource: str) -> None:
        if resource in self._resources:
            return
        self._resources.add(resource)
        if self._interactive:
            with self._lock:
                self.output.write(
                    "\r" + (" " * max(self._live_line_width, 42)) + "\r"
                )
                self._live_line_width = 0
                self.output.flush()
        self._write(f"    {self._symbol('✓', '+')} {resource}")

    def render(self, event) -> None:
        if (
            event.phase == "execution"
            and event.status == "failed"
            and event.event_type in {"execution_progress", "execution_completed"}
        ):
            self._fail("execution")
            return

        if event.event_type == "execution_started":
            self._start("execution")
            return
        if event.event_type == "response_started":
            self._finish("execution")

        failed_phase = self._FAILED_EVENTS.get(event.event_type)
        if failed_phase is not None:
            self._fail(failed_phase)
            return

        if event.event_type == "response_progress":
            if event.status == "failed":
                self._fail("response")
                return
            state = self._active.get("response")
            if state is not None and event.status == "started":
                state["message"] = event.message.lower()
                if not self._interactive:
                    self._write(
                        self._line(
                            self._symbol("›", ">"),
                            "response",
                            self.clock() - state["started"],
                            state["message"],
                        )
                    )
            return

        phase = self._START_EVENTS.get(event.event_type)
        if phase is not None:
            status = {
                "planning": "Creating plan...",
                "execution": "Executing tasks...",
                "response": "Preparing response...",
            }.get(phase, "")
            self._start(phase, status if phase == "response" else "")
            return

        phase = self._END_EVENTS.get(event.event_type)
        if phase is not None:
            self._finish(phase, event.duration_ms)
            if phase == "response":
                self._resources.clear()
            return

        if (
            event.phase == "execution"
            and event.resource
            and event.status == "completed"
            and event.event_type in {"execution_progress", "execution_completed"}
        ):
            self._resource_completed(event.resource)


def _render_progress_event(event) -> None:
    """Compatibility callback backed by the terminal-only presentation filter."""
    _terminal_progress_renderer.output = sys.stdout
    _terminal_progress_renderer._interactive = bool(
        getattr(sys.stdout, "isatty", lambda: False)()
    )
    _terminal_progress_renderer.render(event)


_terminal_progress_renderer = TerminalProgressRenderer()


def _handle_observability_command(query: str, store) -> bool:
    command = query.lower()
    if command not in {"/trace", "/audit", "/metrics"}:
        return False
    if command == "/trace":
        rows = store.recent(10, event_type="execution.completed")
        for row in rows:
            outcome = "success" if row["success"] else "failure"
            print(
                f"{row['request_id'] or '-'} | {row['task_id'] or '-'} | "
                f"{row['capability'] or '-'} | {row['resource'] or '-'} | "
                f"{outcome} | {row['duration_ms'] or 0}ms"
            )
    elif command == "/audit":
        rows = store.recent(10)
        for row in rows:
            if row["event_type"].startswith("execution."):
                continue
            print(
                f"{row['timestamp']} | {row['actor'] or '-'} | "
                f"{row['resource'] or '-'} | {row['action'] or '-'} | "
                f"{row['authorization_decision'] or '-'}"
            )
    else:
        values = store.aggregate_metrics()
        print(
            f"requests={values['total_requests']} "
            f"successes={values['successes']} failures={values['failures']} "
            f"authorization_denials={values['authorization_denials']} "
            f"average_duration_ms={values['average_duration_ms']}"
        )
    return True


def _provider_error_message(error: RuntimeError) -> str:
    """Return a concise interactive message for a provider failure."""
    details = []
    current = error
    while current is not None:
        details.append(str(current).lower())
        current = current.__cause__ or current.__context__

    if any(
        marker in " ".join(details)
        for marker in ("429", "rate limit", "rate_limited", "too many requests")
    ):
        return (
            f"The configured model provider '{get_config().model_provider}' "
            "is temporarily unavailable or rate limited. Please try again later."
        )

    return (
        f"The configured model provider '{get_config().model_provider}' "
        "could not complete the request."
    )


def main():
    if sys.stdout.isatty() and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    agent = create_real_agent()
    if hasattr(agent, "progress_reporter"):
        agent.progress_reporter.callback = TerminalProgressRenderer().render
    actor = DEFAULT_ACTOR
    session_id = "terminal-session"
    store = get_observability_store(
        getattr(get_config(), "observability_db_path", None)
    )

    print("=" * 60)
    print("Vexux AI Interactive Terminal")
    print("Type 'exit' or 'quit' to stop. Use '/actor investigator' or '/actor support_user'.")
    print("Resource-aware fraud queries use the real Neo4j and MySQL resources.")
    runtime = provider_diagnostic(get_config())
    print(f"Model: {runtime.get('model', runtime['provider'])}")
    print(f"Runtime: {runtime['runtime_mode']}")
    print("=" * 60)

    while True:
        query = input("\nYou: ").strip()

        if query.lower() in {"exit", "quit"}:
            print("Exiting...")
            break

        if _handle_observability_command(query, store):
            continue

        if query.lower().startswith("/actor "):
            requested_actor = query.split(None, 1)[1].strip()
            try:
                actor = validate_actor(requested_actor)
            except ValueError as exc:
                print(f"Actor error: {exc}")
                continue
            print(f"Actor: {actor}")
            continue

        if not query:
            continue

        try:
            agent.resource_router.route(query)
        except ValueError as exc:
            print(f"\nRouting error: {exc}")

        try:
            result = agent.run(query, session_id=session_id, user_id=actor)
        except RuntimeError as exc:
            LOGGER.error("Interactive model provider request failed.", exc_info=exc)
            print(f"\nError: {_provider_error_message(exc)}")
            continue

        if result.output is not None:
            print("\nAgent:")
            print(result.output)

        if result.error:
            print("\nError:")
            print(result.error)

        timings = getattr(result, "metadata", {}).get("timings_ms", {})
        if timings:
            for phase in ("setup_routing", "other"):
                duration = timings.get(phase, 0) / 1000.0
                if duration >= 0.01:
                    label = "Setup/routing" if phase == "setup_routing" else "Other"
                    print(f"{label:<16}{duration:.2f}s")
            print(
                f"{'Total':<16}"
                f"{timings.get('total', 0) / 1000:.2f}s"
            )


if __name__ == "__main__":
    main()
