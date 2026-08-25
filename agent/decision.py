from enum import Enum

from core.contracts.observation import Observation


class DecisionType(Enum):

    DONE = "done"

    REPLAN = "replan"


class DecisionMaker:

    def decide(
        self,
        observation: Observation,
    ) -> DecisionType:

        # Observations created for blocked/skipped tasks carry metadata{"blocked": True}
        # Treat blocked tasks as non-replanning outcomes: they are controlled skips.
        if observation.metadata and observation.metadata.get("blocked"):
            return DecisionType.DONE

        if observation.success:
            return DecisionType.DONE

        return DecisionType.REPLAN