from core.contracts.execution import (
    AgentContext,
    Plan,
    Task,
)

from core.contracts.observation import Observation


class SessionState:

    def __init__(self, history_limit: int = 10, actor_id: str | None = None):

        self.history_limit = history_limit
        self.actor_id = actor_id
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
        self._sessions: dict[object, SessionState] = {}

    @staticmethod
    def _session_key(session_id: str, user_id: str | None) -> object:
        return (session_id, user_id) if user_id is not None else session_id

    def create(
        self,
        request_id: str,
        session_id: str | None = None,
        user_id: str | None = None,
        security_context=None,
    ) -> AgentContext:

        history = []

        if session_id is not None:

            session = self._sessions.setdefault(
                self._session_key(session_id, user_id),
                SessionState(self.history_limit, user_id),
            )

            history = list(session.history)

        return AgentContext(
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            security_context=security_context,
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
            self._session_key(context.session_id, context.user_id),
            SessionState(self.history_limit, context.user_id),
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