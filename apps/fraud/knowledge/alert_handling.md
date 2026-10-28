# Alert Handling Reference

This document is project reference guidance for the Vexux-AI fraud
demonstration. Alert descriptions are illustrative concepts, not official bank
policy or regulatory requirements.

## Severity and lifecycle

Severity communicates the priority assigned to an alert by its producing
system; it is not, by itself, a final fraud determination. An alert can be
open while it awaits review or action, and can be closed after a documented
resolution. Preserve the recorded status and severity when describing an
operational alert.

An alert may be associated with a transaction and a customer. Investigations
are separate case records with their own lifecycle. Review the link between
these records in their authoritative data source rather than inferring an
investigation from alert text alone.

## Reviewing open high-severity alerts

An open high-severity alert warrants timely review under the applicable
operational process. Confirm the customer and transaction identifiers, inspect
the underlying transaction details, and look for independent supporting or
contradictory evidence. Consider whether related alerts describe the same event
so duplicate notifications are not mistaken for independent signals.

Document the evidence reviewed, the disposition, and any follow-up needed.
Escalate when material evidence remains unexplained or when the established
process requires additional review. Do not infer a customer's final risk
assessment solely from the alert's severity.

## Closing and escalation

Close an alert only when its disposition is supported by the relevant records
and the responsible process permits closure. Retain the relationship between
the alert and any investigation or event record. If an alert is closed, that
status does not erase the underlying transaction or prove that no concern
existed.
