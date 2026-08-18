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

        if observation.success:
            return DecisionType.DONE

        return DecisionType.REPLAN