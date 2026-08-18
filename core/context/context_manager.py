from core.contracts.execution import (
    AgentContext,
    Plan,
    Task,
)

from core.contracts.observation import Observation


class ContextManager:

    def create(
        self,
        request_id: str,
    ) -> AgentContext:

        return AgentContext(
            request_id=request_id
        )

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