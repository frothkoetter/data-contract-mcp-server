from __future__ import annotations

import json

import pytest
from pytest_httpserver import HTTPServer
from werkzeug.wrappers import Response

from data_contract_mcp_server.client import AtlasClient
from data_contract_mcp_server.data_contracts import (
    DATA_CONTRACT_TYPE_VERSION,
    atlas_struct_array_to_writer,
    build_data_contract_attributes,
    build_entity_typedef_upgrade,
    build_qualified_name,
    build_schema_summary,
    derive_freshness_quality_threshold,
    derive_freshness_sla,
    flatten_schema_for_atlas,
    parse_quality_rules,
    parse_schema_objects,
    parse_enforcement_default_action,
    parse_enforcement_mode,
    parse_enforcement_policies,
    parse_struct_quality_rules,
    parse_struct_sla_properties,
    parse_table_bindings,
    data_contract_typedef_status,
    typedef_needs_upgrade,
)


@pytest.fixture
def atlas(httpserver: HTTPServer) -> AtlasClient:
    import requests

    session = requests.Session()
    session.verify = True
    return AtlasClient(httpserver.url_for(""), session, timeout_seconds=5)


def test_parse_enforcement_policies() -> None:
    policies = parse_enforcement_policies(
        [
            {
                "name": "freshness-block",
                "trigger": "quality_violation",
                "action": "block_and_alert",
                "ruleFilter": "freshness",
                "severity": "critical",
                "notifyChannel": "slack",
                "notifyTargets": ["#alerts", "owner@example.com"],
                "rangerPolicyTemplate": "deny_read",
            }
        ]
    )
    assert policies[0]["name"] == "freshness-block"
    assert policies[0]["trigger"] == "quality_violation"
    assert policies[0]["action"] == "block_and_alert"
    assert policies[0]["rule_filter"] == "freshness"
    assert policies[0]["notify_targets"] == "#alerts, owner@example.com"


def test_parse_enforcement_policies_validates_enums() -> None:
    with pytest.raises(ValueError, match="trigger must be one of"):
        parse_enforcement_policies([{"name": "x", "trigger": "invalid", "action": "alert"}])
    with pytest.raises(ValueError, match="action must be one of"):
        parse_enforcement_policies(
            [{"name": "x", "trigger": "quality_violation", "action": "invalid"}]
        )
    with pytest.raises(ValueError, match="duplicate enforcement policy name"):
        parse_enforcement_policies(
            [
                {"name": "dup", "trigger": "manual", "action": "alert"},
                {"name": "dup", "trigger": "manual", "action": "log_only"},
            ]
        )


def test_parse_enforcement_mode_and_default_action() -> None:
    assert parse_enforcement_mode("enforce") == "enforce"
    assert parse_enforcement_default_action("alert") == "alert"
    with pytest.raises(ValueError, match="enforcement_mode must be one of"):
        parse_enforcement_mode("invalid")
    with pytest.raises(ValueError, match="enforcement_default_action must be one of"):
        parse_enforcement_default_action("invalid")


def test_parse_struct_quality_rules_severity_and_enforcement_policy() -> None:
    rules = parse_struct_quality_rules(
        [
            {
                "metric": "freshness",
                "threshold": "24",
                "unit": "h",
                "severity": "critical",
                "businessImpact": "regulatory",
                "enforcementPolicy": "freshness-block",
            }
        ]
    )
    assert rules[0]["severity"] == "critical"
    assert rules[0]["business_impact"] == "regulatory"
    assert rules[0]["enforcement_policy"] == "freshness-block"


def test_build_data_contract_attributes_includes_enforcement() -> None:
    policies = parse_enforcement_policies(
        [{"name": "warn", "trigger": "sla_violation", "action": "alert"}]
    )
    attrs = build_data_contract_attributes(
        qualified_name="c1@1.0",
        contract_id="c1",
        version="1.0",
        status="active",
        enforcement_policies=policies,
        enforcement_default_action="alert",
        enforcement_mode="monitor",
        auto_mark_broken_on_critical=True,
        ranger_service="cm_hive",
    )
    assert attrs["enforcement_policies"][0]["name"] == "warn"
    assert attrs["enforcement_default_action"] == "alert"
    assert attrs["enforcement_mode"] == "monitor"
    assert attrs["auto_mark_broken_on_critical"] is True
    assert attrs["ranger_service"] == "cm_hive"


def test_build_qualified_name() -> None:
    assert build_qualified_name("orders", "1.0") == "orders@1.0"


def test_parse_quality_rules() -> None:
    assert parse_quality_rules("a, b") == ["a", "b"]
    assert parse_quality_rules('["x", "y"]') == ["x", "y"]


def test_parse_quality_rules_accepts_native_list() -> None:
    assert parse_quality_rules(["rule a", "rule b"]) == ["rule a", "rule b"]
    assert parse_quality_rules([{"description": "PK must be unique"}]) == ["PK must be unique"]


def test_parse_consumers_accepts_native_list() -> None:
    from data_contract_mcp_server.data_contracts import parse_consumers

    assert parse_consumers(["role:risk-analyst", "group:finance", "person:jane.doe"]) == [
        "role:risk-analyst",
        "group:finance",
        "person:jane.doe",
    ]
    assert parse_consumers("team-a, team-b") == ["team-a", "team-b"]


def test_build_data_contract_attributes_includes_consumer() -> None:
    attrs = build_data_contract_attributes(
        qualified_name="c1@1.0",
        contract_id="c1",
        version="1.0",
        status="draft",
        consumer=["group:risk-analytics", "person:frothkoe"],
    )
    assert attrs["consumer"] == ["group:risk-analytics", "person:frothkoe"]


def test_parse_schema_objects_accepts_native_list_with_column_aliases() -> None:
    parsed = parse_schema_objects(
        [
            {
                "name": "mart_credit_quality_matrix",
                "logicalType": "object",
                "properties": [
                    {
                        "column_name": "icas_rating",
                        "data_type": "int",
                        "nullable": "NO",
                        "description": "ICAS rating category",
                    }
                ],
            }
        ]
    )
    assert parsed[0]["properties"][0]["name"] == "icas_rating"
    assert parsed[0]["properties"][0]["physical_type"] == "int"
    assert parsed[0]["properties"][0]["is_required"] is True
    parsed = parse_schema_objects(
        json.dumps(
            [
                {
                    "name": "orders",
                    "logicalType": "object",
                    "physicalType": "table",
                    "properties": [
                        {
                            "name": "id",
                            "logicalType": "string",
                            "physicalType": "varchar(18)",
                            "primaryKey": True,
                        }
                    ],
                }
            ]
        )
    )
    assert parsed[0]["logical_type"] == "object"
    assert parsed[0]["properties"][0]["primary_key"] is True


def test_flatten_schema_for_atlas() -> None:
    schema = parse_schema_objects(
        json.dumps(
            [
                {
                    "name": "orders",
                    "logicalType": "object",
                    "properties": [{"name": "id", "logicalType": "string"}],
                }
            ]
        )
    )
    objects, properties = flatten_schema_for_atlas(schema)
    assert objects[0]["name"] == "orders"
    assert "properties" not in objects[0]
    assert properties[0]["object_name"] == "orders"
    assert properties[0]["name"] == "id"


def test_build_schema_summary() -> None:
    schema = parse_schema_objects(
        json.dumps([{"name": "a", "properties": [{"name": "x"}, {"name": "y"}]}, {"name": "b"}])
    )
    objects, properties = flatten_schema_for_atlas(schema)
    assert build_schema_summary(objects, properties) == "2 objects, 2 properties"


def test_derive_freshness_fields() -> None:
    sla = parse_struct_sla_properties(
        json.dumps([{"property": "freshness", "value": 24, "unit": "h"}])
    )
    quality = parse_struct_quality_rules(
        json.dumps([{"metric": "freshness", "mustBeLessThan": 24, "unit": "h"}])
    )
    assert derive_freshness_sla(sla) == "24h"
    assert derive_freshness_quality_threshold(quality) == "24h"


def test_build_data_contract_attributes_sets_derived_fields() -> None:
    schema = parse_schema_objects(
        json.dumps([{"name": "orders", "properties": [{"name": "updated_at"}]}])
    )
    quality = parse_struct_quality_rules(
        json.dumps([{"metric": "freshness", "threshold": "24", "unit": "h"}])
    )
    sla = parse_struct_sla_properties(
        json.dumps([{"property": "freshness", "value": "1", "unit": "d"}])
    )
    attrs = build_data_contract_attributes(
        qualified_name="c1@1.0",
        contract_id="c1",
        version="1.0",
        status="draft",
        schema_objects=schema,
        quality=quality,
        sla_properties=sla,
    )
    assert attrs["schema_summary"] == "1 objects, 1 properties"
    assert attrs["schema_properties"][0]["object_name"] == "orders"
    assert attrs["freshness_quality_threshold"] == "24h"
    assert attrs["freshness_sla"] == "1d"


def test_typedef_needs_upgrade() -> None:
    assert typedef_needs_upgrade({"typeVersion": "1.0"}) is True
    assert typedef_needs_upgrade({"typeVersion": DATA_CONTRACT_TYPE_VERSION}) is True
    assert typedef_needs_upgrade(
        {
            "typeVersion": DATA_CONTRACT_TYPE_VERSION,
            "attributeDefs": [{"name": "contractId"}, {"name": "domain"}],
        }
    ) is True
    assert typedef_needs_upgrade(
        {
            "typeVersion": DATA_CONTRACT_TYPE_VERSION,
            "superTypes": ["Referenceable"],
            "serviceType": "data_mesh",
            "attributeDefs": [{"name": attr["name"]} for attr in __import__(
                "data_contract_mcp_server.data_contracts", fromlist=["_DATA_CONTRACT_V2_ATTRS"]
            )._DATA_CONTRACT_V2_ATTRS],
        }
    ) is False


def test_data_contract_typedef_status_reports_missing_enforcement_fields() -> None:
    status = data_contract_typedef_status(
        {
            "typeVersion": "2.2",
            "attributeDefs": [{"name": "contractId"}, {"name": "status"}, {"name": "version"}],
        }
    )
    assert status["needsUpgrade"] is True
    assert status["expectedTypeVersion"] == DATA_CONTRACT_TYPE_VERSION
    assert "enforcement_policies" in status["missingAttributes"]
    assert "ranger_service" in status["missingAttributes"]


def test_build_entity_typedef_upgrade_preserves_super_types() -> None:
    existing = {
        "name": "data_contract",
        "typeVersion": "1.0",
        "superTypes": ["Referenceable"],
        "serviceType": "data_mesh",
        "attributeDefs": [{"name": "contractId"}, {"name": "status"}],
    }
    upgraded = build_entity_typedef_upgrade(existing)
    assert upgraded["superTypes"] == ["Referenceable"]
    assert upgraded["typeVersion"] == DATA_CONTRACT_TYPE_VERSION
    assert "domain" in {attr["name"] for attr in upgraded["attributeDefs"]}
    assert "contractId" in {attr["name"] for attr in upgraded["attributeDefs"]}


def test_parse_table_bindings_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="Unsupported table_type"):
        parse_table_bindings("db.t@cluster", table_type="kafka_topic")


def test_create_data_contract(atlas: AtlasClient, httpserver: HTTPServer) -> None:
    httpserver.expect_request(
        "/v2/entity/uniqueAttribute/type/data_contract",
        method="GET",
    ).respond_with_data("not found", status=404)
    httpserver.expect_request("/v2/entity", method="POST").respond_with_json(
        {"guidAssignments": {"-1": "guid-1"}, "mutatedEntities": {"CREATE": []}}
    )
    result = atlas.create_data_contract("c1", "1.0", "draft", quality_rules=["rule1"])
    assert result["qualifiedName"] == "c1@1.0"
    assert result["contractId"] == "c1"


def test_create_data_contract_with_odcs_fields(atlas: AtlasClient, httpserver: HTTPServer) -> None:
    captured: dict = {}

    def handler(request):
        captured["body"] = json.loads(request.data.decode())
        return Response(
            json.dumps({"guidAssignments": {"-1": "guid-1"}}),
            status=200,
            mimetype="application/json",
        )

    httpserver.expect_request(
        "/v2/entity/uniqueAttribute/type/data_contract",
        method="GET",
    ).respond_with_data("not found", status=404)
    httpserver.expect_request("/v2/entity", method="POST").respond_with_handler(handler)
    schema = [{"name": "orders", "properties": [{"name": "id", "logical_type": "string"}]}]
    quality = [{"metric": "freshness", "threshold": "24", "unit": "h"}]
    sla = [{"property": "freshness", "value": "24", "unit": "h"}]
    atlas.create_data_contract(
        "c1",
        "1.0",
        "active",
        name="orders_v1",
        domain="sales",
        schema_objects=schema,
        quality=quality,
        sla_properties=sla,
        odcs_document='{"kind":"DataContract"}',
    )
    attrs = captured["body"]["entity"]["attributes"]
    assert attrs["name"] == "orders_v1"
    assert attrs["domain"] == "sales"
    assert attrs["freshness_sla"] == "24h"
    assert attrs["freshness_quality_threshold"] == "24h"
    assert attrs["schema_summary"] == "1 objects, 1 properties"
    assert attrs["schema_properties"][0]["object_name"] == "orders"
    assert attrs["schema_properties"][0]["name"] == "id"


def test_create_data_contract_with_enforcement_fields(
    atlas: AtlasClient, httpserver: HTTPServer
) -> None:
    captured: dict = {}

    def handler(request):
        captured["body"] = json.loads(request.data.decode())
        return Response(
            json.dumps({"guidAssignments": {"-1": "guid-1"}}),
            status=200,
            mimetype="application/json",
        )

    httpserver.expect_request(
        "/v2/entity/uniqueAttribute/type/data_contract",
        method="GET",
    ).respond_with_data("not found", status=404)
    httpserver.expect_request("/v2/entity", method="POST").respond_with_handler(handler)
    enforcement = [
        {
            "name": "freshness-block",
            "trigger": "quality_violation",
            "action": "block_and_alert",
            "rule_filter": "freshness",
            "notify_targets": ["#alerts"],
        }
    ]
    quality = [
        {
            "metric": "freshness",
            "threshold": "24",
            "unit": "h",
            "severity": "critical",
            "enforcement_policy": "freshness-block",
        }
    ]
    atlas.create_data_contract(
        "c1",
        "1.0",
        "active",
        quality=quality,
        enforcement_policies=enforcement,
        enforcement_mode="enforce",
        enforcement_default_action="alert",
        auto_mark_broken_on_critical=True,
        ranger_service="cm_hive",
    )
    attrs = captured["body"]["entity"]["attributes"]
    assert attrs["enforcement_mode"] == "enforce"
    assert attrs["enforcement_default_action"] == "alert"
    assert attrs["auto_mark_broken_on_critical"] is True
    assert attrs["ranger_service"] == "cm_hive"
    assert attrs["enforcement_policies"][0]["action"] == "block_and_alert"
    assert attrs["quality"][0]["enforcement_policy"] == "freshness-block"


def test_get_data_contract(atlas: AtlasClient, httpserver: HTTPServer) -> None:
    httpserver.expect_request(
        "/v2/entity/uniqueAttribute/type/data_contract",
        method="GET",
    ).respond_with_json(
        {
            "entity": {
                "guid": "guid-1",
                "typeName": "data_contract",
                "attributes": {"qualifiedName": "c1@1.0", "status": "active"},
            }
        }
    )
    result = atlas.get_data_contract(contract_id="c1", version="1.0")
    assert result["entity"]["guid"] == "guid-1"


def test_search_data_contracts_dsl(atlas: AtlasClient, httpserver: HTTPServer) -> None:
    httpserver.expect_request("/v2/search/dsl", method="GET").respond_with_json(
        {"entities": [], "approximateCount": 0}
    )
    result = atlas.search_data_contracts(status="active")
    assert result["approximateCount"] == 0


def test_ensure_data_contract_typedef_exists(atlas: AtlasClient, httpserver: HTTPServer) -> None:
    from data_contract_mcp_server.data_contracts import _DATA_CONTRACT_V2_ATTRS

    httpserver.expect_request("/v2/types/entitydef/name/data_contract", method="GET").respond_with_json(
        {
            "name": "data_contract",
            "typeVersion": DATA_CONTRACT_TYPE_VERSION,
            "superTypes": ["Referenceable"],
            "attributeDefs": _DATA_CONTRACT_V2_ATTRS,
        }
    )
    result = atlas.ensure_data_contract_typedef()
    assert result["status"] == "exists"
    assert result["missingAttributes"] == []


def test_ensure_data_contract_typedef_upgrades(atlas: AtlasClient, httpserver: HTTPServer) -> None:
    httpserver.expect_request("/v2/types/entitydef/name/data_contract", method="GET").respond_with_json(
        {"name": "data_contract", "typeVersion": "1.0"}
    )
    for struct_name in (
        "odcs_schema_property",
        "odcs_schema_object",
        "odcs_quality_rule",
        "odcs_sla_property",
        "odcs_enforcement_policy",
    ):
        httpserver.expect_request(
            f"/v2/types/structdef/name/{struct_name}",
            method="GET",
        ).respond_with_data("not found", status=404)
    httpserver.expect_request("/v2/types/typedefs", method="POST").respond_with_json(
        {"structDefs": [{"name": "odcs_schema_property"}]}
    )
    httpserver.expect_request("/v2/types/typedefs", method="PUT").respond_with_json(
        {"entityDefs": [{"name": "data_contract", "typeVersion": "2.1"}]}
    )
    result = atlas.ensure_data_contract_typedef()
    assert result["status"] == "upgraded"


def test_ensure_data_contract_typedef_creates(atlas: AtlasClient, httpserver: HTTPServer) -> None:
    httpserver.expect_request(
        "/v2/types/entitydef/name/data_contract", method="GET"
    ).respond_with_data("not found", status=404)
    httpserver.expect_request("/v2/types/typedefs", method="POST").respond_with_json(
        {"entityDefs": [{"name": "data_contract"}]}
    )
    result = atlas.ensure_data_contract_typedef()
    assert result["status"] == "created"
    assert result["missingAttributes"] == []


def test_atlas_struct_array_to_writer() -> None:
    converted = atlas_struct_array_to_writer(
        [
            {
                "typeName": "odcs_schema_property",
                "attributes": {
                    "object_name": "orders",
                    "name": "id",
                    "logical_type": "string",
                    "primary_key": False,
                },
            }
        ]
    )
    assert converted == [
        {"object_name": "orders", "name": "id", "logical_type": "string", "primary_key": False}
    ]


def test_update_status_preserves_odcs_attributes(atlas: AtlasClient, httpserver: HTTPServer) -> None:
    httpserver.expect_request(
        "/v2/entity/uniqueAttribute/type/data_contract",
        method="GET",
    ).respond_with_json(
        {
            "entity": {
                "guid": "guid-1",
                "attributes": {
                    "qualifiedName": "c1@1.0",
                    "contractId": "c1",
                    "version": "1.0",
                    "status": "draft",
                    "domain": "sales",
                    "freshness_sla": "24h",
                    "schema_properties": [
                        {
                            "typeName": "odcs_schema_property",
                            "attributes": {
                                "object_name": "orders",
                                "name": "id",
                                "logical_type": "string",
                                "primary_key": False,
                            },
                        }
                    ],
                },
            }
        }
    )
    captured: dict = {}

    def handler(request):
        captured["body"] = json.loads(request.data.decode())
        return Response(
            json.dumps({"mutatedEntities": {"UPDATE": []}}),
            status=200,
            mimetype="application/json",
        )

    httpserver.expect_request("/v2/entity", method="POST").respond_with_handler(handler)
    atlas.update_data_contract_status(contract_id="c1", version="1.0", status="active")
    attrs = captured["body"]["entity"]["attributes"]
    assert attrs["status"] == "active"
    assert attrs["domain"] == "sales"
    assert attrs["freshness_sla"] == "24h"
    assert attrs["schema_properties"][0]["name"] == "id"


def test_delete_data_contract(atlas: AtlasClient, httpserver: HTTPServer) -> None:
    httpserver.expect_request(
        "/v2/entity/uniqueAttribute/type/data_contract",
        method="GET",
    ).respond_with_json({"entity": {"guid": "guid-del", "attributes": {"qualifiedName": "c1@1.0"}}})
    httpserver.expect_request(
        "/v2/entity/guid/guid-del", method="DELETE", query_string="purge=true"
    ).respond_with_data("", status=204)
    httpserver.expect_request("/admin/purge/", method="PUT").respond_with_json({})
    result = atlas.delete_data_contract(contract_id="c1", version="1.0")
    assert result["status"] == "purged"
    assert result["guid"] == "guid-del"
