import logging
import time
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
        policy=None,
        workflow_registry=None,
        memory_registry=None,
        knowledge_graph_registry=None,
    ):

        self.execution_manager = (
            execution_manager
        )

        self.planner = planner

        self.observer = observer

        self.decision_maker = decision_maker

        self.context_manager = context_manager

        self.response_synthesizer = response_synthesizer

        self.policy = policy

        self.workflow_registry = workflow_registry

        self.memory_registry = memory_registry

        # Optional knowledge graph registry (kept optional and backward compatible)
        self.knowledge_graph_registry = knowledge_graph_registry

        self.max_retries = 2

    def run(
        self,
        query: str,
        session_id: str | None = None,
        user_id: str | None = None,
    ):

        context = self.context_manager.create(
            request_id=str(uuid.uuid4()),
            session_id=session_id,
            user_id=user_id,
        )

        if self.policy is not None:
            decision = self.policy.validate_input(query)
            if not decision.allowed:
                return AgentResponse(success=False, error=f"Policy denied input: {decision.reason}", trace=[], metadata={"request_id": context.request_id, "policy": decision.policy_name})

        retry_count = 0
        logger = logging.getLogger(__name__)

        while retry_count <= self.max_retries:

            try:

                if retry_count == 0:

                    plan = self.planner.create_plan(
                        query,
                        conversation_context=context.conversation_history,
                    )

                else:

                    if context.session_id is None:
                        recovery_plan = self.planner.replan(
                            query,
                            context.observations[-1],
                            context.current_task,
                        )
                    else:
                        recovery_plan = self.planner.replan(
                            query,
                            context.observations[-1],
                            context.current_task,
                            conversation_context=context.conversation_history,
                        )

                    # Collect any remaining tasks from the previous plan that have not run yet
                    remaining_tasks = []
                    if context.current_plan and context.current_task:
                        found_current = False
                        for task in context.current_plan.tasks:
                            if found_current:
                                remaining_tasks.append(task)
                            elif task.id == context.current_task.id:
                                found_current = True

                    plan = Plan(
                        tasks=recovery_plan.tasks + remaining_tasks
                    )

            except ValueError as exc:

                return AgentResponse(
                    success=False,
                    output=None,
                    error=f"Planning failed: {exc}",
                    trace=context.observations,
                    metadata={
                        "request_id": context.request_id,
                        "session_id": context.session_id,
                        "user_id": context.user_id,
                    },
                )

            self.context_manager.set_plan(
                context,
                plan,
            )

            if self.workflow_registry is not None:
                expanded_tasks = []
                for task in plan.tasks:
                    if task.metadata.get("capability") != "workflow":
                        expanded_tasks.append(task)
                        continue
                    workflow = self.workflow_registry.get(task.input["workflow"])
                    expanded_tasks.extend(workflow.build_tasks(task.input))
                plan = Plan(tasks=expanded_tasks)
                self.context_manager.set_plan(context, plan)

            if self.policy is not None:
                decision = self.policy.validate_plan(plan, context)
                if not decision.allowed:
                    return AgentResponse(success=False, error=f"Policy denied plan: {decision.reason}", trace=context.observations, metadata={"request_id": context.request_id, "policy": decision.policy_name})

            should_replan = False

            # Build dependency graph structures from the plan tasks
            id_map = {t.id: t for t in plan.tasks}
            adj = {t.id: [] for t in plan.tasks}
            indegree = {t.id: 0 for t in plan.tasks}
            original_index = {t.id: idx for idx, t in enumerate(plan.tasks)}

            for t in plan.tasks:
                for dep in getattr(t, "depends_on", []) or []:
                    if dep in adj:
                        adj[dep].append(t.id)
                        indegree[t.id] += 1

            executed = set()
            failed = set()
            blocked = set()

            # Helper to mark descendants as blocked when a failure occurs
            def mark_descendants_blocked(start_id):
                queue = list(adj.get(start_id, []))
                desc = set()
                while queue:
                    nid = queue.pop(0)
                    if nid in desc:
                        continue
                    desc.add(nid)
                    queue.extend(adj.get(nid, []))
                for did in desc:
                    blocked.add(did)

            # Execute ready tasks deterministically: preserve original plan order among ready tasks
            remaining = set(id_map.keys())
            while remaining:
                # find ready tasks: indegree 0, not executed, not blocked
                ready = [nid for nid in plan.tasks if indegree.get(nid.id, 0) == 0 and nid.id in remaining and nid.id not in blocked]
                # 'ready' uses task objects; preserve original order by sorting using original_index
                ready_ids = [t.id for t in ready]

                if not ready_ids:
                    # No ready tasks found — should not happen due to prior validation (cycles handled there)
                    break

                # Process ready tasks in the deterministic order of their appearance
                for task_id in ready_ids:
                    task = id_map[task_id]

                    # set current task in context
                    self.context_manager.set_task(context, task)

                    started_at = time.perf_counter()
                    result = self.execution_manager.execute(task, context)
                    duration_ms = (time.perf_counter() - started_at) * 1000

                    logger.info(
                        "agent.task.execution",
                        extra={
                            "request_id": context.request_id,
                            "session_id": context.session_id,
                            "user_id": context.user_id,
                            "task_id": task.id,
                            "capability": task.metadata.get("capability"),
                            "execution_success": result.success,
                            "execution_duration_ms": round(duration_ms, 3),
                        },
                    )

                    observation = self.observer.observe(result, task)
                    self.context_manager.add_observation(context, observation)

                    if observation.success:
                        executed.add(task.id)
                        self.context_manager.add_completed_task(context, task)
                        # decrement indegree of children
                        for child in adj.get(task.id, []):
                            indegree[child] -= 1
                            if indegree[child] < 0:
                                indegree[child] = 0

                        # remove from remaining
                        remaining.discard(task.id)

                        # Decision: continue
                        decision = self.decision_maker.decide(observation)
                        if decision == DecisionType.REPLAN:
                            should_replan = True
                            break

                        # else continue to next ready task
                        continue

                    # If observation indicates a blocked/skipped task (due to dependency), treat as non-replanning
                    if observation.metadata and observation.metadata.get("blocked"):
                        # record and don't execute it
                        blocked.add(task.id)
                        remaining.discard(task.id)
                        continue

                    # If task failed (not a blocked skip), mark failed and block descendants
                    failed.add(task.id)
                    # mark descendants as blocked so they won't be executed
                    mark_descendants_blocked(task.id)

                    # create blocked observations for descendants
                    for desc_id in list(blocked):
                        if desc_id in remaining:
                            desc_task = id_map[desc_id]
                            blocked_result = self.execution_manager.execute if False else None
                            # synthesize a blocked ExecutionResult
                            from core.contracts.execution import ExecutionResult

                            blocked_exec = ExecutionResult(success=False, output=None, error=f"Blocked due to failed dependency: {task.id}", metadata={"blocked": True})
                            blocked_obs = self.observer.observe(blocked_exec, desc_task)
                            self.context_manager.add_observation(context, blocked_obs)
                            remaining.discard(desc_id)

                    # Decision: replan for the failure
                    decision = self.decision_maker.decide(observation)
                    if decision == DecisionType.REPLAN:
                        should_replan = True
                        break

                if should_replan:
                    break

            if not should_replan:

                final_output = self.response_synthesizer.synthesize(
                    query,
                    context.observations,
                    conversation_context=context.conversation_history,
                )

                if self.policy is not None:
                    decision = self.policy.validate_output(final_output, context)
                    if not decision.allowed:
                        return AgentResponse(success=False, error=f"Policy denied output: {decision.reason}", trace=context.observations, metadata={"request_id": context.request_id, "policy": decision.policy_name})

                self.context_manager.add_conversation_turn(
                    context,
                    query,
                    final_output,
                )

                return AgentResponse(
                    success=True,
                    output=final_output,
                    error=None,
                    trace=context.observations,
                    metadata={
                        "request_id": context.request_id,
                        "session_id": context.session_id,
                    },
                )

            retry_count += 1

        return AgentResponse(
            success=False,
            output=None,
            error="Agent could not complete the request.",
            trace=context.observations,
            metadata={
                "request_id": context.request_id,
                "session_id": context.session_id,
                "user_id": context.user_id,
            },
        )
