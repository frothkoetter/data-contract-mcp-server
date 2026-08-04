from __future__ import annotations

from data_contract_mcp_server.griffin import (
    GRIFFIN_DSL_TYPE,
    GRIFFIN_ENGINE,
    build_completeness_rule,
    build_timeliness_rule,
    build_uniqueness_rule,
    column_from_element,
    infer_dq_type,
    infer_griffin_rule,
    normalize_griffin_quality_rule,
)
from data_contract_mcp_server.data_contracts import parse_struct_quality_rules


def test_column_from_element() -> None:
    assert column_from_element("orders.updated_at") == "updated_at"
    assert column_from_element("reporting_bank_bic") == "reporting_bank_bic"
    assert column_from_element(None) is None


def test_build_completeness_rule() -> None:
    assert build_completeness_rule("reporting_bank_bic") == "reporting_bank_bic"
    assert build_completeness_rule(["name", "age"]) == "name, age"


def test_build_timeliness_rule() -> None:
    assert build_timeliness_rule("updated_at") == "updated_at"
    assert build_timeliness_rule("ts", "out_ts") == "ts, out_ts"


def test_build_uniqueness_rule() -> None:
    assert build_uniqueness_rule("id") == "id"
    assert build_uniqueness_rule(["name", "age"]) == "name, age"


def test_infer_dq_type_from_metric_and_rule_type() -> None:
    assert infer_dq_type({"metric": "freshness"}) == "timeliness"
    assert infer_dq_type({"metric": "not_null_count"}) == "completeness"
    assert infer_dq_type({"rule_type": "completeness"}) == "completeness"
    assert infer_dq_type({"dq_type": "accuracy"}) == "accuracy"


def test_infer_griffin_rule_completeness() -> None:
    rule = infer_griffin_rule(
        {"element": "reporting_bank_bic", "metric": "not_null_count"},
        "completeness",
    )
    assert rule == "reporting_bank_bic"


def test_infer_griffin_rule_timeliness() -> None:
    rule = infer_griffin_rule(
        {"element": "orders.updated_at", "metric": "freshness"},
        "timeliness",
    )
    assert rule == "updated_at"


def test_normalize_griffin_quality_rule_auto_fills_fields() -> None:
    normalized = normalize_griffin_quality_rule(
        {
            "name": "DQ_NOT_NULL_reporting_bank_bic",
            "rule_type": "completeness",
            "metric": "not_null_count",
            "element": "reporting_bank_bic",
            "threshold": 0,
        }
    )
    assert normalized["engine"] == GRIFFIN_ENGINE
    assert normalized["dsl_type"] == GRIFFIN_DSL_TYPE
    assert normalized["dq_type"] == "completeness"
    assert normalized["rule"] == "reporting_bank_bic"


def test_normalize_griffin_quality_rule_preserves_explicit_rule() -> None:
    normalized = normalize_griffin_quality_rule(
        {
            "engine": "griffin",
            "dsl_type": "griffin-dsl",
            "dq_type": "profiling",
            "rule": "source.id.count() AS id_count, source.age.max() AS age_max",
        }
    )
    assert normalized["rule"] == "source.id.count() AS id_count, source.age.max() AS age_max"


def test_parse_struct_quality_rules_griffin_completeness() -> None:
    rules = parse_struct_quality_rules(
        [
            {
                "name": "DQ_NOT_NULL_reporting_bank_bic",
                "description": "Ensure reporting_bank_bic is not null for all records.",
                "rule_type": "completeness",
                "metric": "not_null_count",
                "threshold": 0,
                "severity": "critical",
                "enforcement_policy": "block_access_on_violation",
                "business_impact": (
                    "Null BIC codes prevent correct bank-level aggregation and reporting."
                ),
                "element": "reporting_bank_bic",
            }
        ]
    )
    rule = rules[0]
    assert rule["engine"] == GRIFFIN_ENGINE
    assert rule["dsl_type"] == GRIFFIN_DSL_TYPE
    assert rule["dq_type"] == "completeness"
    assert rule["rule"] == "reporting_bank_bic"
    assert rule["threshold"] == "0"
    assert rule["enforcement_policy"] == "block_access_on_violation"


def test_parse_struct_quality_rules_griffin_timeliness() -> None:
    rules = parse_struct_quality_rules(
        [
            {
                "metric": "freshness",
                "threshold": "24",
                "unit": "h",
                "element": "orders.updated_at",
                "severity": "critical",
                "enforcementPolicy": "freshness-block",
            }
        ]
    )
    assert rules[0]["dq_type"] == "timeliness"
    assert rules[0]["rule"] == "updated_at"
    assert rules[0]["enforcement_policy"] == "freshness-block"
