"""Deterministic lexical and structural checks for held-out evaluation answers."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


PROPERTY_RULES: dict[str, tuple[tuple[str, ...], ...]] = {
    "attribute_observation": ((r"\b(observation|observed|record(?:s|ed)?|documented|data shows|evidence shows)\b",),),
    "avoid_assumption": ((r"\b(do not|don't|should not|must not|avoid|cannot)\s+(assume|infer|presume|conclude)\b|\b(alternative explanations|other explanations|check for legitimate use)\b",),),
    "do_not_assume": ((r"\b(do not|don't|should not|must not|avoid|cannot)\s+(assume|infer|presume|conclude)\b|\b(alternative explanations|other explanations|check for legitimate use)\b",),),
    "avoid_duplicate_corroboration": ((r"\b(same event|duplicate|not independent|count(?:ing)? .{0,24}twice|double count)\b",),),
    "check_event_identity": (
        (r"\b(event|notification|alert|record)\b",),
        (r"\b(same|identity|reference|identifier|match|duplicate)\b",),
    ),
    "clear_general_explanation": ((r"\b(because|means|refers to|helps?|allows|is used to|can help|this is why|in order to)\b",),),
    "define_metric_and_population": (
        (r"\b(velocity|rate|count|frequency|volume|metric|measure|number of transactions)\b",),
        (r"\b(account|customer|population|transactions?|per\b|across)\b",),
    ),
    "defined_time_window": ((r"\b(time window|time period|within \d+|per (hour|day|week|month)|\d+ (hours?|days?|weeks?|months?)|daily|weekly|monthly)\b",),),
    "deterministic_assessment_authority": ((r"\b(deterministic|configured workflow|configured process|official assessment|authoritative system)\b",),),
    "do_not_fabricate_relationships": (
        (r"\b(do not|don't|cannot|should not|must not|not possible|no basis to)\b",),
        (r"\b(infer|invent|fabricat|assume|establish|determine)\b",),
        (r"\b(relationship|connection|link|graph|account)\b",),
    ),
    "do_not_invent_alerts_or_connections": (
        (r"\b(do not|don't|cannot|can't|no access|not available|not provided|must not)\b",),
        (r"\b(invent|fabricat|confirm|provide|retrieve|look up|verify)\b",),
        (r"\b(alert|connection|relationship|operational record)\b",),
    ),
    "do_not_invent_transactions": (
        (r"\b(do not|don't|cannot|can't|no access|not available|not provided|must not)\b",),
        (r"\b(invent|fabricat|confirm|provide|list|retrieve|look up|verify)\b",),
        (r"\b(transaction|operational record)\b",),
    ),
    "document_disposition": (
        (r"\b(document|record|note|log)\b",),
        (r"\b(disposition|decision|status|reason|outcome|resolution|action taken|follow-up)\b",),
    ),
    "document_escalation_reason": (
        (r"\b(document|record|note|log)\b",),
        (r"\b(escalat\w*|reason|basis|rationale)\b",),
    ),
    "does_not_establish_intent": (
        (r"\b(does not|doesn't|cannot|can't|not by itself|doesn't necessarily)\b",),
        (r"\b(establish|prove|show|identify|demonstrate|determine)\b",),
        (r"\b(intent|motive|purpose)\b",),
    ),
    "does_not_identify_operator": (
        (r"\b(does not|doesn't|cannot|can't|not by itself|does not tell)\b",),
        (r"\b(identify|establish|show|tell|determine|prove)\b",),
        (r"\b(operator|who used|who controlled|person|individual|identity)\b",),
    ),
    "explain_scope": ((r"\b(scope|limited to|only includes|covers|population|applies to)\b",),),
    "guidance_not_customer_evidence": (
        (r"\b(policy|guidance|general knowledge|general information)\b",),
        (r"\b(not|does not|cannot|isn't|without)\b",),
        (r"\b(customer evidence|customer-specific evidence|operational evidence|case evidence|prove the case)\b",),
    ),
    "identify_conflict": ((r"\b(conflict|conflicting|discrepanc\w*|inconsisten\w*|contradict\w*)\b",),),
    "legitimate_shared_use": ((r"\b(legitimate|household|family|workplace|work device|shared use|multiple users|common device|caregiver)\b",),),
    "material_evidence_or_converging_signals": (
        (r"\b(material|corroborat\w*|converg\w*|independent|multiple)\b",),
        (r"\b(evidence|signal|finding|observation|indicator)\b",),
    ),
    "no_customer_assessment": (
        (r"\b(cannot|can't|should not|do not|not enough|insufficient|requires|must not)\b",),
        (r"\b(customer|individual|case|risk|assessment|assess)\b",),
    ),
    "no_guilt_claim": (
        (r"\b(not|does not|cannot|should not|avoid|no basis to)\b",),
        (r"\b(guilt|guilty|intent|culpability|accuse|blame|proof)\b",),
    ),
    "no_invented_risk": (
        (r"\b(do not|don't|cannot|can't|should not|not enough|no basis to)\b",),
        (r"\b(assign|invent|infer|declare|claim|determine|label)\b",),
        (r"\b(risk|score|rating|category|assessment)\b",),
    ),
    "no_universal_threshold_claim": (
        (r"\b(no|not a|not an|avoid|should not claim|does not define)\b",),
        (r"\b(universal|standard|fixed|official)\b",),
        (r"\b(threshold|cutoff|cut-off|benchmark|limit)\b",),
    ),
    "policy_not_operational_evidence": (
        (r"\b(policy|guidance|general rule)\b",),
        (r"\b(not|does not|cannot|isn't|doesn't)\b",),
        (r"\b(operational evidence|customer facts|current alerts|transactions|relationships|case evidence)\b",),
    ),
    "preserve_source_attribution": (
        (r"\b(source|record|system|report|document)\b",),
        (r"\b(attribute|identify|specify|cite|state|distinguish|who reported|which source)\b",),
    ),
    "preserve_sources": ((r"\b(preserve|retain|cite|record|document|list)\b",), (r"\b(source|sources|records|evidence)\b",)),
    "qualify_uncertainty": ((r"\b(may|might|could|possible|possibly|uncertain|unclear|not necessarily|does not establish|cannot conclude)\b",),),
    "refuse_invented_score": (
        (r"\b(cannot|can't|will not|won't|should not|do not|not appropriate|no basis to)\b",),
        (r"\b(assign|invent|create|calculate|provide|give)\b",),
        (r"\b(score|rating|number)\b",),
    ),
    "report_source_unavailable": (
        (r"\b(unavailable|not available|cannot access|can't access|unable to access|not accessible|not provided|offline)\b",),
        (r"\b(source|database|system|graph|records|data)\b",),
    ),
    "requires_authorized_operational_lookup": (
        (r"\b(authori[sz]ed|permission|access-controlled)\b",),
        (r"\b(operational|customer|transaction|case)\b",),
        (r"\b(lookup|look up|query|retrieve|check|consult|records|system)\b",),
    ),
    "requires_authorized_sources": (
        (r"\b(authori[sz]ed|permission|access-controlled)\b",),
        (r"\b(source|record|system|data)\b",),
    ),
    "requires_corroboration": ((r"\b(corroborat\w*|independent evidence|additional evidence|converging signals|cross-check)\b",),),
    "review_underlying_records": (
        (r"\b(review|examine|check|inspect|verify)\b",),
        (r"\b(underlying|original|source|transaction|event|alert|account)\b",),
        (r"\b(record|data|document|evidence|details)\b",),
    ),
    "separate_fact_and_interpretation": (
        (r"\b(separate|distinguish|differentiate|label|identify)\b",),
        (r"\b(fact|observation|verified|recorded)\b",),
        (r"\b(interpretation|hypothesis|inference|assumption)\b",),
    ),
    "severity_not_assessment": (
        (r"\b(severity|priority|alert level)\b",),
        (r"\b(not|does not|doesn't|cannot|isn't|not automatically)\b",),
        (r"\b(risk|assessment|fraud|customer category|final category)\b",),
    ),
    "signal_not_proof": (
        (r"\b(signal|indicator|association|pattern|alert)\b",),
        (r"\b(not proof|not evidence of|does not prove|doesn't prove|does not establish|cannot by itself establish|does not by itself prove|is not conclusive|not conclusive)\b",),
    ),
    "state_aggregation_scope": (
        (r"\b(aggregation|aggregate|scope|include|specify|define)\b",),
        (r"\b(account|subject|time|currency|status|population|transaction)\b",),
    ),
    "state_limitation": ((r"\b(cannot|can't|unable|without|limitation|not available|do not have|does not provide|not enough)\b",),),
    "subject_and_account_scope": ((r"\b(subject|customer|account|profile|population)\b",),),
    "time_currency_status": (
        (r"\b(time|date|timestamp|period|window)\b",),
        (r"\b(currency|amount|status|settled|pending|reversed)\b",),
    ),
    "use_configured_process": (
        (r"\b(configured|approved|established|defined)\b",),
        (r"\b(process|workflow|policy|procedure|threshold|criteria)\b",),
    ),
    "use_deterministic_authority": (
        (r"\b(deterministic|configured workflow|official workflow|authoritative system|authorized system)\b",),
        (r"\b(assessment|decision|risk|result|source|authority)\b",),
    ),
    "verify_authoritative_source": (
        (r"\b(verify|check|confirm|consult|use)\b",),
        (r"\b(authoritative|authori[sz]ed|official|system of record)\b",),
        (r"\b(source|record|system|database)\b",),
    ),
    "verify_context": ((r"\b(verify|check|understand|establish|consider)\b",), (r"\b(context|purpose|legitimate|circumstance|role|reason)\b",)),
    "verify_identifiers": (
        (r"\b(verify|check|confirm|match|validate)\b",),
        (r"\b(identifier|id\b|account|customer|transaction|alert|event)\b",),
    ),
    "wait_for_verified_records": (
        (r"\b(wait|obtain|retrieve|consult|use|only after|until)\b",),
        (r"\b(verified|authoritative|confirmed|available)\b",),
        (r"\b(record|data|source|evidence|system)\b",),
    ),
}


def _score_structural_property(
    property_name: str,
    prompt: str,
    output: str,
) -> tuple[bool, list[str]]:
    if property_name == "one_sentence":
        sentence_endings = re.findall(r"[.!?](?:\s|$)", output.strip())
        passed = bool(output.strip()) and len(sentence_endings) <= 1
        return passed, ["at most one sentence-ending punctuation mark"] if passed else []

    numbered_lines = re.findall(r"(?m)^\s*\d+[.)]\s+\S.*$", output)
    if property_name == "two_numbered_steps":
        passed = len(numbered_lines) == 2
        return passed, ["exactly two numbered lines"] if passed else []
    if property_name == "follow_format":
        if re.search(r"\bexactly two numbered steps\b", prompt, re.IGNORECASE):
            passed = len(numbered_lines) == 2
            return passed, ["exactly two numbered lines"] if passed else []
        return True, ["no deterministic format constraint encoded"]
    if property_name == "correct_order":
        read = re.search(r"\bread\b", output, re.IGNORECASE)
        summarize = re.search(r"\bsummar(?:y|ize|ise|izing|ising)\b", output, re.IGNORECASE)
        passed = bool(read and summarize and read.start() < summarize.start())
        return passed, ["read precedes summarize"] if passed else []
    raise KeyError(f"No structural evaluation rule exists for {property_name!r}.")


def score_property(
    property_name: str,
    prompt: str,
    output: str,
) -> dict[str, Any]:
    if property_name in {"one_sentence", "two_numbered_steps", "follow_format", "correct_order"}:
        passed, evidence = _score_structural_property(property_name, prompt, output)
    else:
        clauses = PROPERTY_RULES.get(property_name)
        if clauses is None:
            raise KeyError(f"No deterministic evaluation rule exists for {property_name!r}.")
        matched = [
            next(
                (
                    re.search(pattern, output, re.IGNORECASE | re.DOTALL)
                    for pattern in alternatives
                    if re.search(pattern, output, re.IGNORECASE | re.DOTALL)
                ),
                None,
            )
            for alternatives in clauses
        ]
        passed = all(match is not None for match in matched)
        evidence = [match.group(0) for match in matched if match is not None]
    return {"passed": passed, "evidence": evidence}


def score_properties(
    prompt: str,
    output: str,
    property_names: list[str],
) -> dict[str, Any]:
    results = {
        name: score_property(name, prompt, output)
        for name in property_names
    }
    return {
        "properties": results,
        "passed": sum(result["passed"] for result in results.values()),
        "total": len(results),
    }


def summarize_comparison(results: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, dict[str, int]] = {
        mode: {"passed": 0, "total": 0}
        for mode in ("base", "adapter")
    }
    categories: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: {
            mode: {"passed": 0, "total": 0}
            for mode in ("base", "adapter")
        }
    )
    changes = {"improvements": 0, "regressions": 0, "unchanged": 0}
    category_changes: dict[str, dict[str, int]] = defaultdict(
        lambda: {"improvements": 0, "regressions": 0, "unchanged": 0}
    )
    change_details = []

    for case_index, case in enumerate(results):
        category = case["category"]
        for mode in ("base", "adapter"):
            score = case[f"{mode}_score"]
            totals[mode]["passed"] += score["passed"]
            totals[mode]["total"] += score["total"]
            categories[category][mode]["passed"] += score["passed"]
            categories[category][mode]["total"] += score["total"]
        for name in case["expected_properties"]:
            base_passed = case["base_score"]["properties"][name]["passed"]
            adapter_passed = case["adapter_score"]["properties"][name]["passed"]
            if adapter_passed and not base_passed:
                changes["improvements"] += 1
                category_changes[category]["improvements"] += 1
                outcome = "improvement"
            elif base_passed and not adapter_passed:
                changes["regressions"] += 1
                category_changes[category]["regressions"] += 1
                outcome = "regression"
            else:
                changes["unchanged"] += 1
                category_changes[category]["unchanged"] += 1
                outcome = "unchanged"
            change_details.append(
                {
                    "index": case.get("index", case_index),
                    "category": category,
                    "property": name,
                    "base_passed": base_passed,
                    "adapter_passed": adapter_passed,
                    "outcome": outcome,
                }
            )

    category_results = {}
    for category, values in sorted(categories.items()):
        category_results[category] = {
            **values,
            "property_changes": category_changes[category],
        }
    return {
        "scoring_method": "deterministic lexical/structural cues; not semantic accuracy",
        "totals": totals,
        "categories": category_results,
        "property_changes": changes,
        "property_change_details": change_details,
    }


def add_comparison_scores(result: dict[str, Any]) -> dict[str, Any]:
    scored_results = []
    for case in result["results"]:
        scored_case = dict(case)
        scored_case["base_score"] = score_properties(
            case["prompt"],
            case["base_output"],
            case["expected_properties"],
        )
        scored_case["adapter_score"] = score_properties(
            case["prompt"],
            case["adapter_output"],
            case["expected_properties"],
        )
        scored_results.append(scored_case)
    result["results"] = scored_results
    result["deterministic_summary"] = summarize_comparison(scored_results)
    return result
