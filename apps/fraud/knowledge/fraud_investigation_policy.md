# Fraud Investigation Reference Policy

This document is project reference guidance for the Vexux-AI fraud
demonstration. It is not an official bank policy, legal standard, or
regulatory interpretation.

## Investigation workflow

Begin with a clearly identified subject and a defined investigative question.
Collect relevant operational records from their authoritative systems, such as
transaction records from the business database and relationship evidence from
the graph. Record what was observed, where it came from, and any material
limitations. Reconcile identifiers across sources before drawing conclusions.

Use this guidance to support consistent review, not to replace the deterministic
workflow or its source data. If records conflict, are incomplete, or cannot be
verified, describe the uncertainty and seek appropriate review rather than
filling gaps with assumptions.

## Evidence and assessment

Keep observations separate from interpretations. A transaction row, alert, or
graph relationship is evidence with a source; a risk assessment is a separate
conclusion produced by the application's deterministic assessment logic.
General policy text cannot establish that a particular customer performed an
action or has a particular risk level.

An investigator should be able to explain which observed signals support a
review and distinguish corroborated facts from hypotheses. Do not convert
guidance, similarity scores, or retrieved prose into a numeric fraud score.

## Escalation and investigator responsibilities

Escalate for appropriate human review when source evidence is credible and
material, when several independent signals converge, or when an unresolved
discrepancy could affect a decision. Preserve relevant context and document
the reason for escalation. Do not treat a single weak indicator as proof of
fraud.

Investigators should use only authorized resources, follow the configured
access policy, and avoid exposing unrelated customer information. Retrieval
of general guidance does not authorize access to operational customer records.
