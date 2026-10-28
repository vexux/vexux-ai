# Transaction Monitoring Reference

This document is project reference guidance for the Vexux-AI fraud
demonstration. It describes general monitoring concepts and does not prescribe
official thresholds or represent bank or regulatory policy.

## Velocity and unusual activity

Transaction velocity describes activity over a defined time window, such as
the count or aggregate value of transactions in that period. A rapid sequence
can merit review when it differs materially from the expected context, but
velocity alone is not proof of fraud. The time window, population, and metric
must be understood before comparing activity.

Unusual activity can also involve a change in amount, timing, merchant,
location, or transaction outcome. Interpret these indicators in context and
check whether records refer to distinct transactions.

## Aggregation and investigation

When reviewing activity, aggregate only records that match the intended
customer, account, time interval, currency, and transaction status. Verify
ownership links and timestamps at the source. Explain the aggregation scope
and do not imply that a configured demonstration threshold is an external
standard.

Repeated or high-value activity may justify further investigation when
corroborated by independent evidence or a relevant alert. Review supporting
records and counter-evidence, then follow the application's authorized,
deterministic workflow. Policy guidance can explain why a pattern may deserve
attention; only operational data can establish which transactions occurred.
