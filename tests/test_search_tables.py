from __future__ import annotations

import pytest
from pytest_httpserver import HTTPServer

from data_contract_mcp_server.client import AtlasClient


@pytest.fixture
def atlas(httpserver: HTTPServer) -> AtlasClient:
    import requests

    session = requests.Session()
    session.verify = True
    return AtlasClient(httpserver.url_for(""), session, timeout_seconds=5)


def test_search_tables_uses_hive_and_iceberg_dsl(atlas: AtlasClient, httpserver: HTTPServer) -> None:
    httpserver.expect_oneshot_request("/v2/search/dsl", method="GET").respond_with_json(
        {
            "entities": [
                {
                    "guid": "hive-1",
                    "typeName": "hive_table",
                    "attributes": {
                        "name": "sales",
                        "qualifiedName": "analytics.sales@cluster",
                        "db": {"name": "analytics"},
                    },
                }
            ]
        }
    )
    httpserver.expect_oneshot_request("/v2/search/dsl", method="GET").respond_with_json(
        {
            "entities": [
                {
                    "guid": "iceberg-1",
                    "typeName": "iceberg_table",
                    "attributes": {
                        "name": "sales",
                        "qualifiedName": "analytics.sales@cluster-iceberg",
                        "db": {"name": "analytics"},
                    },
                }
            ]
        }
    )

    result = atlas.search_tables(
        database_name="analytics",
        table_name="sales",
        limit=10,
    )

    assert result["count"] == 2
    assert result["searchedTypes"] == ["hive_table", "iceberg_table"]
    assert {entity["typeName"] for entity in result["entities"]} == {
        "hive_table",
        "iceberg_table",
    }

    dsl_queries = [
        request.query_string.decode()
        for request, _response in httpserver.log
        if request.path == "/v2/search/dsl"
    ]
    assert len(dsl_queries) == 2
    assert any("hive_table" in query and "analytics" in query for query in dsl_queries)
    assert any("iceberg_table" in query and "analytics" in query for query in dsl_queries)


def test_search_tables_basic_fallback_searches_both_types(
    atlas: AtlasClient, httpserver: HTTPServer
) -> None:
    httpserver.expect_request("/v2/search/dsl", method="GET").respond_with_json({"entities": []})
    httpserver.expect_oneshot_request("/v2/search/basic", method="GET").respond_with_json(
        {
            "entities": [
                {
                    "guid": "hive-1",
                    "typeName": "hive_table",
                    "attributes": {"name": "sales", "qualifiedName": "analytics.sales@cluster"},
                }
            ]
        }
    )
    httpserver.expect_oneshot_request("/v2/search/basic", method="GET").respond_with_json(
        {
            "entities": [
                {
                    "guid": "iceberg-1",
                    "typeName": "iceberg_table",
                    "attributes": {
                        "name": "sales",
                        "qualifiedName": "analytics.sales@cluster-iceberg",
                    },
                }
            ]
        }
    )

    result = atlas.search_tables(table_name="sales", limit=10)

    assert result["count"] == 2
    assert result["searchedTypes"] == ["hive_table", "iceberg_table"]
    basic_requests = [
        request.query_string.decode()
        for request, _response in httpserver.log
        if request.path == "/v2/search/basic"
    ]
    assert any("typeName=hive_table" in query for query in basic_requests)
    assert any("typeName=iceberg_table" in query for query in basic_requests)


def test_search_dsl_passes_type_name(atlas: AtlasClient, httpserver: HTTPServer) -> None:
    httpserver.expect_request("/v2/search/dsl", method="GET").respond_with_json({"entities": []})

    result = atlas.search_dsl(type_name="iceberg_table", limit=5)

    assert result["entities"] == []
    assert httpserver.log[0][0].query_string
    assert b"typeName=iceberg_table" in httpserver.log[0][0].query_string
