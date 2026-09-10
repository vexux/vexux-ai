from core.policy.default import DefaultPolicy, PolicyDecision
from apps.fraud.identity import TRUSTED_ACTORS


class FraudPolicy(DefaultPolicy):
    """Application-specific policy for fraud investigation resources.

    The Vexux core remains domain-neutral. This policy is a thin application-layer
    policy that can deny access to fraud investigations for particular actors.
    """

    def __init__(self, deny_map=None):
        super().__init__()
        self.deny_map = deny_map or {}

    def validate_actor(self, actor):
        if actor not in TRUSTED_ACTORS:
            return PolicyDecision(False, "Actor identity is not registered.", "identity")
        return PolicyDecision(True, policy_name="identity")

    def authorize_resource(self, actor, resource_type, resource_name, action, context=None):
        if resource_type == "knowledge_graph":
            denied = self.deny_map.get(resource_type, set())
            if resource_name in denied or (actor == "support_user" and resource_name == "fraud_graph"):
                return PolicyDecision(
                    False,
                    f"Access to {resource_type}:{resource_name} denied for actor {actor}",
                    policy_name="fraud",
                )
        return super().authorize_resource(actor, resource_type, resource_name, action, context)


__all__ = ["FraudPolicy"]
