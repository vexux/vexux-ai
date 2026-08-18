import uuid

from agent.execution_manager import (
    ExecutionManager,
)

from agent.planner import Planner
from agent.observer import Observer
from agent.decision import DecisionMaker, DecisionType
from core.contracts.execution import Plan
from core.contracts.response import AgentResponse
from core.context.context_manager import ContextManager
from agent.response_synthesizer import ResponseSynthesizer

class Agent:

    def __init__(
        self,
        execution_manager: ExecutionManager,
        planner: Planner,
        observer: Observer,
        decision_maker: DecisionMaker,
        context_manager: ContextManager,
        response_synthesizer: ResponseSynthesizer,
    ):

        self.execution_manager = (
            execution_manager
        )

        self.planner = planner

        self.observer = observer

        self.decision_maker = decision_maker

        self.context_manager = context_manager

        self.response_synthesizer = response_synthesizer

        self.max_retries = 2

    def run(
        self,
        query: str,
    ):

        context = self.context_manager.create(
            request_id=str(uuid.uuid4())
        )

        retry_count = 0

        while retry_count <= self.max_retries:

            if retry_count == 0:

                intent = self.planner.understand_intent(
                    query
                )

                plan = self.planner.create_plan(
                    query,
                    intent,
                )

            else:

                recovery_plan = self.planner.replan(
                    query,
                    context.observations[-1],
                    context.current_task,
                )

                # Collect any remaining tasks from the previous plan that have not run yet
                remaining_tasks = []
                if context.current_plan and context.current_task:
                    found_current = False
                    for t in context.current_plan.tasks:
                        if found_current:
                            remaining_tasks.append(t)
                        elif t.id == context.current_task.id:
                            found_current = True

                plan = Plan(
                    tasks=recovery_plan.tasks + remaining_tasks
                )

            self.context_manager.set_plan(
                context,
                plan,
            )

            should_replan = False

            for task in plan.tasks:

                self.context_manager.set_task(
                    context,
                    task,
                )

                result = self.execution_manager.execute(
                    task,
                    context,
                )

                observation = self.observer.observe(
                    result,
                    task,
                )

                self.context_manager.add_observation(
                    context,
                    observation,
                )

                if observation.success:
                    self.context_manager.add_completed_task(
                        context,
                        task,
                    )

                decision = self.decision_maker.decide(
                    observation
                )

                if decision == DecisionType.DONE:

                    continue

                if decision == DecisionType.REPLAN:

                    should_replan = True
                    break

            if not should_replan:

                final_output = self.response_synthesizer.synthesize(
                    query,
                    context.observations,
                )

                return AgentResponse(
                    success=True,
                    output=final_output,
                    error=None,
                    trace=context.observations,
                )

            retry_count += 1

        return AgentResponse(
            success=False,
            output=None,
            error="Agent could not complete the request.",
            trace=context.observations,
        )