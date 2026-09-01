import logging
import time
import uuid

from agent.execution_manager import (
    ExecutionManager,
)

from agent.planner import Planner
from agent.observer import Observer
from agent.decision import DecisionMaker, DecisionType
from core.contracts.execution import Plan, Task
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
        resource_router=None,
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
        self.resource_router = resource_router

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

        routed_plan = None
        if self.resource_router is not None:
            if self.resource_router.is_authorization_query(query):
                try:
                    selections = self.resource_router.select(query)
                except (ValueError, KeyError) as exc:
                    return AgentResponse(
                        success=False,
                        error=f"Authorization resource resolution failed: {exc}",
                        trace=[],
                        metadata={"request_id": context.request_id, "user_id": user_id},
                    )
                if not selections:
                    return AgentResponse(
                        success=False,
                        output=None,
                        error="Authorization question did not identify a specific registered resource.",
                        trace=[],
                        metadata={"request_id": context.request_id, "user_id": user_id},
                    )
                decisions = []
                for selection in selections:
                    if self.policy is None:
                        decisions.append(f"{selection.name} -> AUTHORIZATION POLICY UNAVAILABLE")
                        continue
                    decision = self.policy.authorize_resource(
                        user_id,
                        selection.resource_type,
                        selection.name,
                        "read",
                        {"request_id": context.request_id},
                    )
                    status = "ALLOWED" if decision.allowed else "DENIED"
                    decisions.append(f"{selection.name} -> {status}")
                return AgentResponse(
                    success=all("ALLOWED" in decision for decision in decisions),
                    output="\n".join(decisions),
                    error=None,
                    trace=[],
                    metadata={
                        "request_id": context.request_id,
                        "user_id": user_id,
                        "authorization_check": True,
                    },
                )
            try:
                route = self.resource_router.route(query)
            except (ValueError, KeyError) as exc:
                return AgentResponse(
                    success=False,
                    error=f"Resource routing failed: {exc}",
                    trace=[],
                    metadata={"request_id": context.request_id, "user_id": user_id},
                )
            if route is not None:
                routed_tasks = []
                if route.graph_requests:
                    graph_input = {
                        "query": query,
                        "graph_requests": route.graph_requests,
                    }
                    if len(route.graph_requests) == 1:
                        request = route.graph_requests[0]
                        graph_input.update({
                            "source": request["graph_name"],
                            "operation": request["operation"],
                            "params": request["params"],
                        })
                        graph_input.pop("graph_requests")
                    routed_tasks.append(Task(
                        id="routed_graphs",
                        description="Retrieve explicitly requested graph resources",
                        input=graph_input,
                        metadata={"capability": "retrieval"},
                    ))
                for index, source_task in enumerate(route.source_tasks, start=1):
                    routed_tasks.append(Task(
                        id=f"routed_source_{index}",
                        description=f"Retrieve explicitly requested source {source_task['source']}",
                        input=source_task,
                        metadata={"capability": "retrieval"},
                    ))
                routed_plan = Plan(tasks=routed_tasks)

        retry_count = 0
        logger = logging.getLogger(__name__)

        while retry_count <= self.max_retries:

            try:

                if retry_count == 0:
                    plan = routed_plan or self.planner.create_plan(
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
                try:
                    # Expand workflows into concrete tasks, validating workflow inputs and generated tasks
                    expanded_tasks = []

                    def _collect_from_task_inputs(obj, refs):
                        # recursively collect any {'from_task': id} references
                        if isinstance(obj, dict):
                            if "from_task" in obj:
                                refs.add(obj.get("from_task"))
                            else:
                                for v in obj.values():
                                    _collect_from_task_inputs(v, refs)
                        elif isinstance(obj, list):
                            for v in obj:
                                _collect_from_task_inputs(v, refs)

                    for task in plan.tasks:
                        if task.metadata.get("capability") != "workflow":
                            expanded_tasks.append(task)
                            continue

                        # Validate workflow input contract minimally (supports 'required' key)
                        workflow_name = task.input.get("workflow")
                        workflow = self.workflow_registry.get(workflow_name)
                        schema = getattr(workflow, "input_schema", None) or {}
                        required = schema.get("required", [])
                        missing = [r for r in required if r not in task.input]
                        if missing:
                            raise ValueError(f"Workflow '{workflow_name}' missing required inputs: {missing}")

                        # Build tasks from workflow
                        wf_tasks = workflow.build_tasks(task.input)

                        # Validate uniqueness of IDs within workflow tasks
                        ids = [t.id for t in wf_tasks]
                        if len(ids) != len(set(ids)):
                            raise ValueError(f"Workflow '{workflow_name}' produced duplicate task IDs")

                        # Build id map for validation
                        id_map_wf = {t.id: t for t in wf_tasks}

                        # Validate depends_on references exist and no self-deps
                        for t in wf_tasks:
                            for dep in getattr(t, "depends_on", []) or []:
                                if dep not in id_map_wf:
                                    raise ValueError(f"Workflow '{workflow_name}' task '{t.id}' has unknown dependency: {dep}")
                                if dep == t.id:
                                    raise ValueError(f"Workflow '{workflow_name}' task '{t.id}' has self-dependency")

                        # Detect cycles using Kahn's algorithm on workflow task graph
                        adj_wf = {tid: [] for tid in ids}
                        indeg_wf = {tid: 0 for tid in ids}
                        for t in wf_tasks:
                            for dep in getattr(t, "depends_on", []) or []:
                                adj_wf[dep].append(t.id)
                                indeg_wf[t.id] += 1
                        # Kahn
                        q = [n for n, d in indeg_wf.items() if d == 0]
                        seen = 0
                        while q:
                            n = q.pop(0)
                            seen += 1
                            for c in adj_wf.get(n, []):
                                indeg_wf[c] -= 1
                                if indeg_wf[c] == 0:
                                    q.append(c)
                        if seen != len(ids):
                            raise ValueError(f"Workflow '{workflow_name}' task graph contains cycles")

                        # Validate that any from_task references in task inputs are declared as dependencies
                        for t in wf_tasks:
                            refs = set()
                            _collect_from_task_inputs(t.input, refs)
                            for refid in refs:
                                if refid not in getattr(t, "depends_on", []) and refid in id_map_wf:
                                    raise ValueError(f"Workflow '{workflow_name}' task '{t.id}' references output from '{refid}' but does not declare it in depends_on")

                        # All validations passed for this workflow - append its tasks to expanded list
                        expanded_tasks.extend(wf_tasks)

                    plan = Plan(tasks=expanded_tasks)
                    self.context_manager.set_plan(context, plan)
                except ValueError as exc:
                    return AgentResponse(
                        success=False,
                        output=None,
                        error=f"Workflow validation failed: {exc}",
                        trace=context.observations,
                        metadata={
                            "request_id": context.request_id,
                            "session_id": context.session_id,
                            "user_id": context.user_id,
                        },
                    )

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

            # Small helper to resolve structured references in task input using context.observations
            def resolve_references(obj):
                # recursively walk obj and replace dicts of form {"from_task":"<id>", "path":"a.b"} with the referenced value
                from core.contracts.execution import ExecutionResult

                def _resolve(value):
                    # primitive
                    if isinstance(value, dict):
                        # detect reference
                        if "from_task" in value:
                            from_task = value.get("from_task")
                            path = value.get("path")
                            # find the latest observation for the referenced task
                            ref_obs = None
                            for o in reversed(context.observations):
                                if o.task_id == from_task:
                                    ref_obs = o
                                    break
                            if ref_obs is None:
                                # synthesize resolution failure
                                raise KeyError(f"Referenced task not found: {from_task}")
                            if not ref_obs.success:
                                raise ValueError(f"Referenced task did not complete successfully: {from_task}")
                            out = ref_obs.output
                            # resolve optional simple dot-path
                            if path:
                                parts = path.split(".")
                                for p in parts:
                                    if isinstance(out, dict) and p in out:
                                        out = out[p]
                                    else:
                                        raise KeyError(f"Path '{path}' not found in output of task {from_task}")
                            return out
                        # else recurse into dict
                        newd = {}
                        for k, v in value.items():
                            newd[k] = _resolve(v)
                        return newd
                    elif isinstance(value, list):
                        return [_resolve(v) for v in value]
                    else:
                        return value

                return _resolve(obj)

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
                        # resolve references in task.input using observations in context
                        try:
                            resolved_input = resolve_references(task.input)
                        except KeyError as kerr:
                            from core.contracts.execution import ExecutionResult

                            # create a failed ExecutionResult due to reference resolution error
                            err_msg = f"Reference resolution error: {kerr}"
                            failed_result = ExecutionResult(success=False, output=None, error=err_msg, metadata={"reference_error": True})
                            observation = self.observer.observe(failed_result, task)
                            self.context_manager.add_observation(context, observation)
                            # mark descendants blocked and synthesize blocked observations
                            failed.add(task.id)
                            mark_descendants_blocked(task.id)
                            for desc_id in list(blocked):
                                if desc_id in remaining:
                                    desc_task = id_map[desc_id]
                                    blocked_exec = ExecutionResult(success=False, output=None, error=f"Blocked due to failed dependency: {task.id}", metadata={"blocked": True})
                                    blocked_obs = self.observer.observe(blocked_exec, desc_task)
                                    self.context_manager.add_observation(context, blocked_obs)
                                    remaining.discard(desc_id)
                            # Decision: replan because resolution failure is a real failure
                            decision = self.decision_maker.decide(observation)
                            if decision == DecisionType.REPLAN:
                                should_replan = True
                                break
                            else:
                                continue
                        except ValueError as verr:
                            from core.contracts.execution import ExecutionResult

                            err_msg = f"Reference resolution error: {verr}"
                            failed_result = ExecutionResult(success=False, output=None, error=err_msg, metadata={"reference_error": True})
                            observation = self.observer.observe(failed_result, task)
                            self.context_manager.add_observation(context, observation)
                            failed.add(task.id)
                            mark_descendants_blocked(task.id)
                            for desc_id in list(blocked):
                                if desc_id in remaining:
                                    desc_task = id_map[desc_id]
                                    blocked_exec = ExecutionResult(success=False, output=None, error=f"Blocked due to failed dependency: {task.id}", metadata={"blocked": True})
                                    blocked_obs = self.observer.observe(blocked_exec, desc_task)
                                    self.context_manager.add_observation(context, blocked_obs)
                                    remaining.discard(desc_id)
                            decision = self.decision_maker.decide(observation)
                            if decision == DecisionType.REPLAN:
                                should_replan = True
                                break
                            else:
                                continue

                        # Run synchronously on main thread using a shallow copy of the task with resolved input
                        exec_task = type(task)(**{k: getattr(task, k) for k in ("id", "description", "input", "metadata", "depends_on")})
                        exec_task.input = resolved_input

                        self.context_manager.set_task(context, task)
                        started_at = time.perf_counter()
                        result = self.execution_manager.execute(exec_task, context)
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
                        # resolve references in task.input using observations in context before submitting
                        try:
                            resolved_input = resolve_references(task.input)
                        except Exception as e:
                            # resolution failed before submission: synthesize a failed ExecutionResult and process it in main thread
                            from core.contracts.execution import ExecutionResult

                            err_msg = f"Reference resolution error before execution: {e}"
                            failed_result = ExecutionResult(success=False, output=None, error=err_msg, metadata={"reference_error": True})
                            observation = self.observer.observe(failed_result, task)
                            self.context_manager.add_observation(context, observation)
                            failed.add(task.id)
                            mark_descendants_blocked(task.id)
                            for desc_id in list(blocked):
                                if desc_id in remaining:
                                    desc_task = id_map[desc_id]
                                    blocked_exec = ExecutionResult(success=False, output=None, error=f"Blocked due to failed dependency: {task.id}", metadata={"blocked": True})
                                    blocked_obs = self.observer.observe(blocked_exec, desc_task)
                                    self.context_manager.add_observation(context, blocked_obs)
                                    remaining.discard(desc_id)
                            # Since this task failed pre-submission, treat as decision to replan if needed
                            decision = self.decision_maker.decide(observation)
                            if decision == DecisionType.REPLAN:
                                should_replan = True
                                break
                            else:
                                continue

                        # Submit worker; worker must not mutate shared AgentContext
                        exec_task = type(task)(**{k: getattr(task, k) for k in ("id", "description", "input", "metadata", "depends_on")})
                        exec_task.input = resolved_input
                        futures[pool.submit(_exec_task, exec_task)] = task.id

                    if should_replan:
                        # skip waiting on remaining futures if replanning triggered during resolution
                        # let the context manager handle already recorded observations; break main loop
                        break

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

    def run_workflow(
        self,
        workflow_name: str,
        workflow_input: dict | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
    ):
        if self.workflow_registry is None:
            return AgentResponse(
                success=False,
                error=f"Workflow '{workflow_name}' is unavailable.",
                trace=[],
                metadata={"selected_mode": "workflow", "workflow_name": workflow_name},
            )

        try:
            self.workflow_registry.get(workflow_name)
        except KeyError:
            return AgentResponse(
                success=False,
                error=f"Unknown workflow: {workflow_name}",
                trace=[],
                metadata={"selected_mode": "workflow", "workflow_name": workflow_name},
            )

        context = self.context_manager.create(
            request_id=str(uuid.uuid4()),
            session_id=session_id,
            user_id=user_id,
        )
        plan = Plan(tasks=[
            Task(
                id=f"workflow:{workflow_name}",
                description=f"Execute workflow '{workflow_name}'",
                input={"workflow": workflow_name, **(workflow_input or {})},
                metadata={"capability": "workflow", "workflow": workflow_name},
            )
        ])

        _, response = self._execute_plan(context, f"Workflow execution: {workflow_name}", plan)
        if response is not None:
            return response

        return AgentResponse(
            success=False,
            output=None,
            error="Workflow execution could not complete.",
            trace=context.observations,
            metadata={
                "request_id": context.request_id,
                "session_id": context.session_id,
                "user_id": context.user_id,
                "selected_mode": "workflow",
                "workflow_name": workflow_name,
            },
        )
