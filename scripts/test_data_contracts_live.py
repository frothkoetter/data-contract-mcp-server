#!/usr/bin/env python3
"""Live integration test for data contract MCP client methods.

Requires env vars: ATLAS_GATEWAY_URL, ATLAS_USER, ATLAS_PASS (or KNOX_TOKEN).
Optional: pass path to a Claude Desktop-style config JSON via --config.

Usage:
  export ATLAS_GATEWAY_URL="https://..."
  export ATLAS_USER="..."
  export ATLAS_PASS="..."
  uv run python scripts/test_data_contracts_live.py

  uv run python scripts/test_data_contracts_live.py --config conf.yaml
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from data_contract_mcp_server.config import ServerConfig
from data_contract_mcp_server.server import build_client


def load_config_env(config_path: Path) -> None:
    payload = json.loads(config_path.read_text())
    servers = payload.get("mcpServers") or {}
    for server in servers.values():
        for key, value in (server.get("env") or {}).items():
            os.environ.setdefault(key, str(value))


def main() -> int:
    parser = argparse.ArgumentParser(description="Live Atlas data contract tests")
    parser.add_argument(
        "--config",
        type=Path,
        help="Claude Desktop-style JSON config with mcpServers.*.env credentials",
    )
    args = parser.parse_args()
    if args.config:
        load_config_env(args.config)

    config = ServerConfig(
        atlas_gateway_url=os.getenv("ATLAS_GATEWAY_URL", ""),
        atlas_user=os.getenv("ATLAS_USER"),
        atlas_password=os.getenv("ATLAS_PASS"),
        knox_token=os.getenv("KNOX_TOKEN"),
        knox_cookie=os.getenv("KNOX_COOKIE"),
    )
    client = build_client(config)
    failures: list[str] = []

    def check(name: str, fn):
        print(f"\n=== {name} ===")
        try:
            result = fn()
            print(json.dumps(result, indent=2)[:2000] if isinstance(result, dict) else result)
            return result
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            print(f"FAIL: {exc}")
            return None

    check("Atlas connectivity", client.get_status)
    typedef_result = check("ensure_data_contract_typedef", client.ensure_data_contract_typedef)
    if typedef_result:
        check(
            "get_entity_type_definition (data_contract v2)",
            lambda: client.get_entity_type_def("data_contract"),
        )

    tables = check(
        "Find hive_table for binding",
        lambda: client.search_basic(query="*", type_name="hive_table", limit=1),
    )
    table_qn = None
    if tables and tables.get("entities"):
        table_qn = tables["entities"][0]["attributes"]["qualifiedName"]
        print(f"Using table: {table_qn}")

    contract_id = f"mcp-test-{int(time.time())}"
    version = "1.0"
    schema_objects = [
        {
            "name": "orders",
            "logical_type": "object",
            "physical_type": "table",
            "properties": [
                {
                    "name": "updated_at",
                    "logical_type": "date",
                    "physical_type": "timestamp",
                },
                {"name": "id", "logical_type": "string", "physical_type": "varchar(36)"},
            ],
        }
    ]
    quality = [
        {
            "rule_type": "timeliness",
            "metric": "freshness",
            "engine": "griffin",
            "dsl_type": "griffin-dsl",
            "dq_type": "timeliness",
            "rule": "updated_at",
            "threshold": "24",
            "unit": "h",
            "element": "orders.updated_at",
        }
    ]
    sla_properties = [{"property": "freshness", "value": "24", "unit": "h"}]

    check(
        "create_data_contract (ODCS hybrid v2)",
        lambda: client.create_data_contract(
            contract_id=contract_id,
            version=version,
            status="draft",
            name=f"{contract_id}_name",
            domain="sales",
            data_product="orders",
            quality_rules=["not_null(id)"],
            schema_objects=schema_objects,
            quality=quality,
            sla_properties=sla_properties,
            odcs_document=json.dumps(
                {
                    "kind": "DataContract",
                    "apiVersion": "v3.0.2",
                    "id": contract_id,
                    "version": version,
                    "status": "draft",
                }
            ),
        ),
    )

    got = check(
        "get_data_contract",
        lambda: client.get_data_contract(contract_id=contract_id, version=version),
    )
    if got:
        attrs = got.get("entity", {}).get("attributes", {})
        if attrs.get("status") != "draft":
            failures.append("get_data_contract: expected status draft")
        if attrs.get("domain") != "sales":
            failures.append("get_data_contract: expected domain sales")
        if not attrs.get("schema_summary"):
            failures.append("get_data_contract: schema_summary missing")
        if attrs.get("freshness_sla") != "24h":
            failures.append(f"get_data_contract: expected freshness_sla 24h, got {attrs.get('freshness_sla')}")
        if attrs.get("freshness_quality_threshold") != "24h":
            failures.append(
                "get_data_contract: expected freshness_quality_threshold 24h, "
                f"got {attrs.get('freshness_quality_threshold')}"
            )
        schema_props = attrs.get("schema_properties") or []
        if len(schema_props) < 2:
            failures.append("get_data_contract: expected at least 2 schema_properties")
        prop_names = {
            (prop.get("attributes") or prop).get("name") for prop in schema_props
        }
        if "id" not in prop_names or "updated_at" not in prop_names:
            failures.append(f"get_data_contract: unexpected schema property names {prop_names}")

    search = check(
        "search_data_contracts (contract_id)",
        lambda: client.search_data_contracts(contract_id=contract_id),
    )
    if search is not None and not search.get("entities"):
        failures.append("search_data_contracts: expected at least one entity")

    check(
        "update_data_contract_status -> active",
        lambda: client.update_data_contract_status(
            contract_id=contract_id, version=version, status="active"
        ),
    )
    got2 = check(
        "get_data_contract (after status update)",
        lambda: client.get_data_contract(contract_id=contract_id, version=version),
    )
    if got2:
        attrs2 = got2.get("entity", {}).get("attributes", {})
        if attrs2.get("status") != "active":
            failures.append("update_data_contract_status: status not active")
        if attrs2.get("domain") != "sales":
            failures.append("update_data_contract_status: domain not preserved")
        if attrs2.get("freshness_sla") != "24h":
            failures.append("update_data_contract_status: freshness_sla not preserved")

    if table_qn:
        check(
            "bind_contract_to_table",
            lambda: client.bind_contract_to_tables(
                table_qualified_names=[{"type_name": "hive_table", "qualified_name": table_qn}],
                contract_id=contract_id,
                version=version,
            ),
        )
        got3 = check(
            "get_data_contract (with relationships)",
            lambda: client.get_data_contract(contract_id=contract_id, version=version),
        )
        rel = (got3 or {}).get("entity", {}).get("relationshipAttributes", {})
        if got3 and not rel.get("assigned_datasets"):
            failures.append("bind_contract_to_table: assigned_datasets missing")
        attrs3 = (got3 or {}).get("entity", {}).get("attributes", {})
        if got3 and attrs3.get("schema_summary") is None:
            failures.append("bind_contract_to_table: schema_summary not preserved")
    else:
        print("\n=== bind_contract_to_table SKIPPED (no hive_table found) ===")

    check(
        "search_data_contracts (status=active)",
        lambda: client.search_data_contracts(status="active", limit=5),
    )

    check(
        "delete_data_contract",
        lambda: client.delete_data_contract(contract_id=contract_id, version=version),
    )

    try:
        client.get_data_contract(contract_id=contract_id, version=version)
        failures.append("delete_data_contract: entity still exists")
    except Exception:
        print("\n=== delete verified (entity not found) ===")

    print("\n" + "=" * 40)
    if failures:
        print(f"FAILED ({len(failures)} issues):")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
