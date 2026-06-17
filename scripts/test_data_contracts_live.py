#!/usr/bin/env python3
"""Live integration test for data contract MCP client methods.

Requires env vars: ATLAS_GATEWAY_URL, ATLAS_USER, ATLAS_PASS (or KNOX_TOKEN).

Usage:
  export ATLAS_GATEWAY_URL="https://..."
  export ATLAS_USER="..."
  export ATLAS_PASS="..."
  .venv/bin/python scripts/test_data_contracts_live.py
"""
from __future__ import annotations

import json
import sys
import time

from data_contract_mcp_server.config import ServerConfig
from data_contract_mcp_server.server import build_client


def main() -> int:
    client = build_client(ServerConfig())
    failures: list[str] = []

    def check(name: str, fn):
        print(f"\n=== {name} ===")
        try:
            result = fn()
            print(json.dumps(result, indent=2)[:1200] if isinstance(result, dict) else result)
            return result
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            print(f"FAIL: {exc}")
            return None

    check("Atlas connectivity", client.get_status)
    check("ensure_data_contract_typedef", client.ensure_data_contract_typedef)

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

    check(
        "create_data_contract",
        lambda: client.create_data_contract(
            contract_id=contract_id,
            version=version,
            status="draft",
            quality_rules=["not_null(id)"],
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
    if got2 and got2.get("entity", {}).get("attributes", {}).get("status") != "active":
        failures.append("update_data_contract_status: status not active")

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
