from __future__ import annotations

import pytest
from pytest_httpserver import HTTPServer

from data_contract_mcp_server.config import ServerConfig
from data_contract_mcp_server.diagnostics import diagnose_atlas_connectivity


@pytest.fixture
def config(httpserver: HTTPServer) -> ServerConfig:
    return ServerConfig(
        atlas_gateway_url=f"{httpserver.url_for('')}/cdp-proxy-api/atlas/api/atlas/",
        atlas_user="user",
        atlas_password="pass",
        timeout_seconds=2,
    )


def test_diagnose_atlas_connectivity_ok(config: ServerConfig, httpserver: HTTPServer) -> None:
    httpserver.expect_request("/cdp-proxy-api/atlas/api/atlas/admin/status", method="GET").respond_with_json(
        {"Status": "ACTIVE"}
    )
    httpserver.expect_request("/cdp-proxy-api/atlas/api/atlas/admin/version", method="GET").respond_with_json(
        {"Version": "2.3.0"}
    )
    httpserver.expect_request(
        "/cdp-proxy-api/atlas/api/atlas/v2/search/basic",
        method="GET",
    ).respond_with_json({"entities": [], "approximateCount": 0})

    report = diagnose_atlas_connectivity(config)

    assert report["overall"] == "ok"
    assert len(report["checks"]) == 4
    assert report["checks"][0]["name"] == "config"
    assert all(check["status"] == "ok" for check in report["checks"][1:])
    assert len(report["curl_commands"]) == 3


def test_diagnose_atlas_connectivity_timeout(config: ServerConfig, httpserver: HTTPServer) -> None:
    import requests

    def hang(_request):
        import time

        time.sleep(3)
        return "late", 200, {"Content-Type": "application/json"}

    httpserver.expect_request(
        "/cdp-proxy-api/atlas/api/atlas/admin/status",
        method="GET",
    ).respond_with_handler(hang)

    session = requests.Session()
    session.auth = ("user", "pass")
    session.verify = True

    report = diagnose_atlas_connectivity(config, session=session)

    assert report["overall"] == "timeout"
    admin_check = next(check for check in report["checks"] if check["name"] == "admin_status")
    assert admin_check["status"] == "timeout"
    assert "timed out" in admin_check["message"].lower()
    assert admin_check.get("curl_command")
    assert report["recommendations"]


def test_diagnose_missing_gateway_url() -> None:
    report = diagnose_atlas_connectivity(
        ServerConfig(atlas_gateway_url="", atlas_user="u", atlas_password="p")
    )

    assert report["overall"] == "failed"
    assert report["checks"][0]["status"] == "failed"
    assert "ATLAS_GATEWAY_URL" in report["checks"][0]["message"]
