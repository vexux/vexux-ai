from typing import Optional
from core.contracts.execution import ExecutionResult, Task
from core.contracts.observation import Observation


class Observer:

    def observe(
        self,
        result: ExecutionResult,
        task: Optional[Task] = None,
    ) -> Observation:

        task_id = task.id if task is not None else None

        if not result.success:

            summary = (
                f"Task '{task.id}' failed: {result.error}"
                if task is not None
                else "The execution failed."
            )

            return Observation(
                success=False,
                output=result.output,
                error=result.error,
                summary=summary,
                task_id=task_id,
            )

        summary = (
            f"Task '{task.id}' completed successfully."
            if task is not None
            else "The execution completed successfully."
        )

        return Observation(
            success=True,
            output=result.output,
            error=None,
            summary=summary,
            task_id=task_id,
        )