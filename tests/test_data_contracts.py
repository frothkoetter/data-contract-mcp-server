from __future__ import annotations

import json

import pytest
from pytest_httpserver import HTTPServer

from atlas_mcp_server.client import AtlasClient
from atlas_mcp_server.data_contracts import (
    build_qualified_name,
    parse_quality_rules,
    parse_table_bindings,
)


@pytest.fixture
def atlas(httpserver: HTTPServer) -> AtlasClient:
    import requests

    session = requests.Session()
    session.verify = True
    return AtlasClient(httpserver.url_for(""), session, timeout_seconds=5)


def test_build_qualified_name() -> None:
    assert build_qualified_name("orders", "1.0") == "orders@1.0"


def test_parse_quality_rules() -> None:
    assert parse_quality_rules("a, b") == ["a", "b"]
    assert parse_quality_rules('["x", "y"]') == ["x", "y"]


def test_parse_table_bindings_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="Unsupported table_type"):
        parse_table_bindings("db.t@cluster", table_type="kafka_topic")


def test_create_data_contract(atlas: AtlasClient, httpserver: HTTPServer) -> None:
    httpserver.expect_request("/v2/entity", method="POST").respond_with_json(
        {"guidAssignments": {"-1": "guid-1"}, "mutatedEntities": {"CREATE": []}}
    )
    result = atlas.create_data_contract("c1", "1.0", "draft", quality_rules=["rule1"])
    assert result["qualifiedName"] == "c1@1.0"
    assert result["contractId"] == "c1"


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
    httpserver.expect_request(
        "/v2/search/dsl",
        method="GET",
        query_string="query=data_contract+where+status%3D%22active%22&limit=25&offset=0",
    ).respond_with_json({"entities": [], "approximateCount": 0})
    result = atlas.search_data_contracts(status="active")
    assert result["approximateCount"] == 0


def test_ensure_data_contract_typedef_exists(atlas: AtlasClient, httpserver: HTTPServer) -> None:
    httpserver.expect_request("/v2/types/entitydef/name/data_contract", method="GET").respond_with_json(
        {"name": "data_contract"}
    )
    result = atlas.ensure_data_contract_typedef()
    assert result["status"] == "exists"


def test_ensure_data_contract_typedef_creates(atlas: AtlasClient, httpserver: HTTPServer) -> None:
    httpserver.expect_request("/v2/types/entitydef/name/data_contract", method="GET").respond_with_data(
        "not found", status=404
    )
    httpserver.expect_request("/v2/types/typedefs", method="POST").respond_with_json(
        {"entityDefs": [{"name": "data_contract"}]}
    )
    result = atlas.ensure_data_contract_typedef()
    assert "entityDefs" in result


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
