from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

GRIFFIN_ENGINE = "griffin"
GRIFFIN_DSL_TYPE = "griffin-dsl"
SPARK_SQL_DSL_TYPE = "spark-sql"

GRIFFIN_DQ_TYPES = frozenset(
    {
        "accuracy",
        "completeness",
        "distinctness",
        "profiling",
        "timeliness",
        "uniqueness",
    }
)

_METRIC_TO_DQ_TYPE: Dict[str, str] = {
    "freshness": "timeliness",
    "not_null_count": "completeness",
    "completeness": "completeness",
    "unique": "uniqueness",
    "uniqueness": "uniqueness",
    "distinctness": "distinctness",
    "accuracy": "accuracy",
    "profiling": "profiling",
}

_RULE_TYPE_TO_DQ_TYPE: Dict[str, str] = {
    "completeness": "completeness",
    "timeliness": "timeliness",
    "uniqueness": "uniqueness",
    "distinctness": "distinctness",
    "accuracy": "accuracy",
    "profiling": "profiling",
    "library": "profiling",
}


def column_from_element(element: Optional[str]) -> Optional[str]:
    """Extract the column name from an ODCS element path (e.g. orders.updated_at -> updated_at)."""
    if not element:
        return None
    text = str(element).strip()
    if not text:
        return None
    return text.rsplit(".", 1)[-1]


def build_completeness_rule(columns: str | Sequence[str]) -> str:
    """Build a Griffin completeness DSL rule (null-check on listed columns)."""
    if isinstance(columns, str):
        return columns.strip()
    return ", ".join(str(col).strip() for col in columns if str(col).strip())


def build_timeliness_rule(
    timestamp_column: str,
    output_column: Optional[str] = None,
) -> str:
    """Build a Griffin timeliness DSL rule (input/output timestamp pair)."""
    ts = timestamp_column.strip()
    if output_column:
        return f"{ts}, {output_column.strip()}"
    return ts


def build_uniqueness_rule(columns: str | Sequence[str]) -> str:
    """Build a Griffin uniqueness DSL rule (duplicate detection on listed columns)."""
    return build_completeness_rule(columns)


def build_profiling_rule(
    *,
    column: str,
    aggregations: Sequence[str],
    source: str = "source",
) -> str:
    """Build a Griffin profiling DSL rule with aggregation functions."""
    col = column.strip()
    src = source.strip() or "source"
    parts = [f"{src}.{col}.{agg}()" for agg in aggregations]
    return ", ".join(parts)


def infer_dq_type(rule: Mapping[str, Any]) -> Optional[str]:
    """Infer the Griffin dq.type from ODCS rule_type or metric fields."""
    explicit = str(rule.get("dq_type") or rule.get("dqType") or "").strip().lower()
    if explicit:
        return explicit

    rule_type = str(rule.get("rule_type") or "").strip().lower()
    if rule_type in _RULE_TYPE_TO_DQ_TYPE:
        return _RULE_TYPE_TO_DQ_TYPE[rule_type]

    metric = str(rule.get("metric") or rule.get("rule") or "").strip().lower()
    if metric in _METRIC_TO_DQ_TYPE:
        return _METRIC_TO_DQ_TYPE[metric]

    return None


def infer_griffin_rule(rule: Mapping[str, Any], dq_type: str) -> Optional[str]:
    """Derive a Griffin DSL rule expression from ODCS fields when not explicitly set."""
    existing = str(rule.get("rule") or "").strip()
    if existing:
        return existing

    element_col = column_from_element(rule.get("element"))

    if dq_type == "completeness":
        if element_col:
            return build_completeness_rule(element_col)
        return None

    if dq_type == "timeliness":
        if element_col:
            return build_timeliness_rule(element_col)
        return None

    if dq_type in {"uniqueness", "distinctness"}:
        if element_col:
            return build_uniqueness_rule(element_col)
        return None

    if dq_type == "profiling":
        metric = str(rule.get("metric") or "").strip().lower()
        if element_col and metric == "not_null_count":
            return f"source.{element_col}.count() where source.{element_col} is not null"
        return None

    return None


def normalize_griffin_quality_rule(rule: Mapping[str, Any]) -> Dict[str, Any]:
    """Ensure quality rules use Apache Griffin DSL fields when engine is griffin or rule is inferable."""
    normalized = dict(rule)

    engine = str(normalized.get("engine") or "").strip().lower()
    dsl_type = str(normalized.get("dsl_type") or normalized.get("dslType") or "").strip().lower()
    has_griffin_rule = bool(str(normalized.get("rule") or "").strip())
    use_griffin = engine == GRIFFIN_ENGINE or dsl_type == GRIFFIN_DSL_TYPE or has_griffin_rule

    dq_type = infer_dq_type(normalized)
    if use_griffin or dq_type:
        normalized.setdefault("engine", GRIFFIN_ENGINE)
        normalized.setdefault("dsl_type", GRIFFIN_DSL_TYPE)
        if dq_type:
            normalized.setdefault("dq_type", dq_type)
            griffin_rule = infer_griffin_rule(normalized, dq_type)
            if griffin_rule and not str(normalized.get("rule") or "").strip():
                normalized["rule"] = griffin_rule

    return normalized
