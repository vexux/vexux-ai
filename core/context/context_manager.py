from core.contracts.execution import (
    AgentContext,
    Plan,
    Task,
)

from core.contracts.observation import Observation


class SessionState:

    def __init__(self, history_limit: int = 10):

        self.history_limit = history_limit
        self.history: list[dict] = []

    def add_turn(self, query: str, response: str) -> None:

        self.history.append(
            {
                "query": query,
                "response": response,
            }
        )

        self.history = self.history[-self.history_limit:]


class ContextManager:

    def __init__(self, history_limit: int = 10):

        if history_limit <= 0:
            raise ValueError("history_limit must be positive")

        self.history_limit = history_limit
        self._sessions: dict[str, SessionState] = {}

    def create(
        self,
        request_id: str,
        session_id: str | None = None,
    ) -> AgentContext:

        history = []

        if session_id is not None:

            session = self._sessions.setdefault(
                session_id,
                SessionState(self.history_limit),
            )

            history = list(session.history)

        return AgentContext(
            request_id=request_id,
            session_id=session_id,
            conversation_history=history,
        )

    def add_conversation_turn(
        self,
        context: AgentContext,
        query: str,
        response: str,
    ) -> None:

        if context.session_id is None:
            return

        session = self._sessions.setdefault(
            context.session_id,
            SessionState(self.history_limit),
        )

        session.add_turn(query, response)

    def set_plan(
        self,
        context: AgentContext,
        plan: Plan,
    ) -> None:

        context.current_plan = plan

    def set_task(
        self,
        context: AgentContext,
        task: Task,
    ) -> None:

        context.current_task = task

    def add_observation(
        self,
        context: AgentContext,
        observation: Observation,
    ) -> None:

        context.observations.append(
            observation
        )

    def add_completed_task(
        self,
        context: AgentContext,
        task: Task,
    ) -> None:

        context.completed_tasks.append(
            task
        )

    def get_latest_observation(
        self,
        context: AgentContext,
    ) -> Observation | None:

        if not context.observations:
            return None

        return context.observations[-1]