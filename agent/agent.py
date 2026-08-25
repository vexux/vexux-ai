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
        # Maximum number of tasks to run in parallel. Default 1 preserves sequential behavior.
        max_parallel_tasks: int = 1,
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

        # concurrency: maximum number of concurrently executing ready tasks
        # default is 1 to preserve previous sequential behavior unless configured
        self.max_parallel_tasks = max(1, int(max_parallel_tasks or 1))

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
                # 'ready' uses task objects; preserve original order by mapping to their ids
                ready_ids = [t.id for t in ready]

                if not ready_ids:
                    # No ready tasks found — should not happen due to prior validation (cycles handled there)
                    break

                # Determine which tasks to submit this batch (preserve original plan order)
                to_submit = ready_ids[: self.max_parallel_tasks]

                # If only one worker configured, keep legacy sequential behavior by executing directly
                if self.max_parallel_tasks <= 1 or len(to_submit) == 1:
                    for task_id in to_submit:
                        task = id_map[task_id]
                        # Run synchronously on main thread
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

                    # batch done; continue to next scheduling loop
                    continue

                # Else: submit multiple tasks concurrently using ThreadPoolExecutor
                from concurrent.futures import ThreadPoolExecutor, as_completed

                futures = {}
                results = {}

                def _exec_task(t):
                    # Worker runs execution_manager.execute and returns tuple
                    start = time.perf_counter()
                    res = self.execution_manager.execute(t, context)
                    duration = (time.perf_counter() - start) * 1000
                    return (t.id, res, duration, t)

                with ThreadPoolExecutor(max_workers=self.max_parallel_tasks) as pool:
                    for tid in to_submit:
                        task = id_map[tid]
                        # Submit worker; worker must not mutate shared AgentContext
                        futures[pool.submit(_exec_task, task)] = task.id

                    # Collect all completed futures
                    completed_batch = []
                    for fut in as_completed(futures):
                        try:
                            tid, res, duration_ms, task = fut.result()
                        except Exception as e:
                            # If worker raised, synthesize a failure ExecutionResult
                            from core.contracts.execution import ExecutionResult

                            tid = futures.get(fut)
                            task = id_map[tid]
                            res = ExecutionResult(success=False, output=None, error=f"Worker exception: {e}")
                            duration_ms = 0.0
                        completed_batch.append((tid, res, duration_ms, task))

                # Process completed_batch in deterministic plan order
                completed_batch.sort(key=lambda item: original_index[item[0]])

                # Track observations for possible replanning selection
                obs_map = {}
                failed_replan_ids = []

                for tid, res, duration_ms, task in completed_batch:
                    logger.info(
                        "agent.task.execution",
                        extra={
                            "request_id": context.request_id,
                            "session_id": context.session_id,
                            "user_id": context.user_id,
                            "task_id": task.id,
                            "capability": task.metadata.get("capability"),
                            "execution_success": res.success,
                            "execution_duration_ms": round(duration_ms, 3),
                        },
                    )

                    # Set current task to the completed task before observing
                    self.context_manager.set_task(context, task)

                    observation = self.observer.observe(res, task)
                    self.context_manager.add_observation(context, observation)
                    obs_map[tid] = observation

                    if observation.success:
                        executed.add(tid)
                        self.context_manager.add_completed_task(context, task)
                        # decrement indegree of children
                        for child in adj.get(tid, []):
                            indegree[child] -= 1
                            if indegree[child] < 0:
                                indegree[child] = 0

                        # remove from remaining
                        remaining.discard(tid)

                        # record decision for successful task
                        decision = self.decision_maker.decide(observation)
                        if decision == DecisionType.REPLAN:
                            # schedule replanning - select this as candidate
                            failed_replan_ids.append(tid)

                        continue

                    # If observation indicates a blocked/skipped task (due to dependency), treat as non-replanning
                    if observation.metadata and observation.metadata.get("blocked"):
                        blocked.add(tid)
                        remaining.discard(tid)
                        continue

                    # If this task failed (not blocked), mark failed and block descendants
                    failed.add(tid)
                    mark_descendants_blocked(tid)

                    # create blocked observations for descendants
                    for desc_id in list(blocked):
                        if desc_id in remaining:
                            desc_task = id_map[desc_id]
                            from core.contracts.execution import ExecutionResult

                            blocked_exec = ExecutionResult(success=False, output=None, error=f"Blocked due to failed dependency: {tid}", metadata={"blocked": True})
                            blocked_obs = self.observer.observe(blocked_exec, desc_task)
                            self.context_manager.add_observation(context, blocked_obs)
                            remaining.discard(desc_id)

                    # decision for failed task
                    decision = self.decision_maker.decide(observation)
                    if decision == DecisionType.REPLAN:
                        failed_replan_ids.append(tid)

                # After processing batch, if replanning is required pick deterministic failed task
                if failed_replan_ids:
                    # pick earliest in original plan order
                    selected = min(failed_replan_ids, key=lambda x: original_index[x])
                    # ensure the corresponding observation is the last one in context.observations
                    sel_obs = obs_map.get(selected)
                    if sel_obs is not None:
                        self.context_manager.add_observation(context, sel_obs)
                    # set current task to the selected failed task for Planner.replan
                    self.context_manager.set_task(context, id_map[selected])
                    should_replan = True
                    break

                # else continue main scheduling loop
                continue

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
