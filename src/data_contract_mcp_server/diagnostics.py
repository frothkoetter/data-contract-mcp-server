from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlparse

import requests
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import SSLError as RequestsSSLError
from requests.exceptions import Timeout as RequestsTimeout

from .auth import AtlasAuthFactory
from .config import ServerConfig

CheckStatus = str  # ok | warning | failed | timeout


def _check(
    name: str,
    status: CheckStatus,
    message: str,
    *,
    url: Optional[str] = None,
    elapsed_ms: Optional[float] = None,
    http_status: Optional[int] = None,
    curl_command: Optional[str] = None,
    recommendation: Optional[str] = None,
) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "name": name,
        "status": status,
        "message": message,
    }
    if url is not None:
        item["url"] = url
    if elapsed_ms is not None:
        item["elapsed_ms"] = round(elapsed_ms, 1)
    if http_status is not None:
        item["http_status"] = http_status
    if curl_command is not None:
        item["curl_command"] = curl_command
    if recommendation is not None:
        item["recommendation"] = recommendation
    return item


def build_curl_probe_commands(config: ServerConfig) -> List[Dict[str, str]]:
    """Shell commands that mirror the MCP connectivity probes (credentials via env)."""
    api_root = config.build_atlas_api_root()
    verify_flag = "-k" if config.build_verify() is False else ""
    ca_flag = f'--cacert "{config.ca_bundle}"' if config.ca_bundle else ""
    tls_flags = " ".join(part for part in (verify_flag, ca_flag) if part).strip()
    timeout = config.timeout_seconds
    auth = '-u "$ATLAS_USER:$ATLAS_PASS"'

    def cmd(label: str, url: str) -> Dict[str, str]:
        curl = (
            f'curl -sS -o /tmp/atlas_diag_body.txt -w "%{{http_code}} %{{time_total}}\\n" '
            f'--connect-timeout 10 -m {timeout} {auth} {tls_flags} '
            f'-H "Accept: application/json" "{url}"'
        ).strip()
        return {"label": label, "url": url, "command": curl}

    return [
        cmd("Atlas admin status (no /v2)", f"{api_root}/admin/status"),
        cmd("Atlas version", f"{api_root}/admin/version"),
        cmd("Atlas v2 search smoke test", f"{api_root}/v2/search/basic?query=*&limit=1"),
    ]


def _diagnose_timeout_message(url: str, timeout_seconds: int) -> str:
    return (
        f"Request to {url} timed out after {timeout_seconds}s. "
        "The Knox gateway or Atlas service may be unreachable, overloaded, or blocked by a firewall."
    )


def _timeout_recommendations(timeout_seconds: int) -> List[str]:
    return [
        f"Increase HTTP_TIMEOUT_SECONDS (currently {timeout_seconds}) if Atlas is slow but healthy.",
        "Run scripts/curl_atlas_diagnostics.sh from a host with CDP network access.",
        "Verify ATLAS_GATEWAY_URL includes the full Knox path: .../cdp-proxy-api/atlas/api/atlas/",
        "Confirm Atlas and Knox pods/services are running in the CDP environment.",
        "Check VPN or corporate proxy settings if connecting from outside the cluster network.",
    ]


def _check_config(config: ServerConfig) -> Dict[str, Any]:
    if not config.atlas_gateway_url:
        return _check(
            "config",
            "failed",
            "ATLAS_GATEWAY_URL is not set.",
            recommendation=(
                "Set ATLAS_GATEWAY_URL to the full Knox Atlas API URL, e.g. "
                "https://<host>/<topology>/cdp-proxy-api/atlas/api/atlas/"
            ),
        )

    parsed = urlparse(config.atlas_gateway_url)
    if parsed.scheme not in {"https", "http"}:
        return _check(
            "config",
            "failed",
            f"ATLAS_GATEWAY_URL must use http or https (got {parsed.scheme!r}).",
            recommendation="Use the HTTPS Knox gateway URL from your CDP DataHub.",
        )

    api_root = config.build_atlas_api_root()
    v2_base = config.build_atlas_base()
    messages = [f"api_root={api_root}", f"v2_base={v2_base}"]

    status: CheckStatus = "ok"
    recommendation: Optional[str] = None
    if "/cdp-proxy-api/atlas" not in config.atlas_gateway_url:
        status = "warning"
        recommendation = (
            "ATLAS_GATEWAY_URL does not contain '/cdp-proxy-api/atlas'. "
            "CDP Knox URLs usually include that path segment."
        )
    if "/v2/v2/" in v2_base or api_root.endswith("/v2/v2"):
        status = "warning"
        recommendation = (
            "Detected a double /v2/ in constructed URLs. "
            "Set ATLAS_GATEWAY_URL to .../atlas/api/atlas/ without a trailing /v2."
        )

    if not config.atlas_user or not config.atlas_password:
        return _check(
            "config",
            "failed",
            "ATLAS_USER and ATLAS_PASS must be set for Basic Auth.",
            recommendation="Export both variables or add them to your MCP server env block.",
        )

    return _check(
        "config",
        status,
        "; ".join(messages),
        recommendation=recommendation,
    )


def _probe_get(
    session: requests.Session,
    url: str,
    *,
    name: str,
    timeout_seconds: int,
) -> Dict[str, Any]:
    curl_command = build_curl_probe_commands_from_url(url, timeout_seconds)
    started = time.perf_counter()
    try:
        resp = session.get(url, timeout=timeout_seconds)
        elapsed_ms = (time.perf_counter() - started) * 1000
    except RequestsTimeout as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        return _check(
            name,
            "timeout",
            _diagnose_timeout_message(url, timeout_seconds),
            url=url,
            elapsed_ms=elapsed_ms,
            curl_command=curl_command,
            recommendation=_timeout_recommendations(timeout_seconds)[0],
        )
    except RequestsConnectionError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        return _check(
            name,
            "failed",
            f"Connection error reaching {url}: {exc}",
            url=url,
            elapsed_ms=elapsed_ms,
            curl_command=curl_command,
            recommendation="Verify DNS, VPN, and that the Knox host is reachable from this machine.",
        )
    except RequestsSSLError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        return _check(
            name,
            "failed",
            f"TLS verification failed for {url}: {exc}",
            url=url,
            elapsed_ms=elapsed_ms,
            curl_command=curl_command,
            recommendation="Set ATLAS_CA_BUNDLE to your CDP CA cert, or ATLAS_VERIFY_SSL=false for testing only.",
        )

    if resp.status_code in {401, 403}:
        return _check(
            name,
            "failed",
            f"HTTP {resp.status_code} — authentication or authorization rejected.",
            url=url,
            elapsed_ms=elapsed_ms,
            http_status=resp.status_code,
            curl_command=curl_command,
            recommendation="Check ATLAS_USER/ATLAS_PASS and Knox SSO authorization for this user.",
        )
    if resp.status_code >= 500:
        body_preview = (resp.text or "")[:300]
        return _check(
            name,
            "failed",
            f"HTTP {resp.status_code} from Atlas/Knox: {body_preview or resp.reason}",
            url=url,
            elapsed_ms=elapsed_ms,
            http_status=resp.status_code,
            curl_command=curl_command,
            recommendation="Inspect Knox/Atlas service logs using the request ID in the response body.",
        )
    if not resp.ok:
        return _check(
            name,
            "failed",
            f"HTTP {resp.status_code}: {resp.reason}",
            url=url,
            elapsed_ms=elapsed_ms,
            http_status=resp.status_code,
            curl_command=curl_command,
        )

    preview = (resp.text or "")[:200]
    return _check(
        name,
        "ok",
        f"HTTP {resp.status_code} in {elapsed_ms:.0f}ms. Body preview: {preview or '(empty)'}",
        url=url,
        elapsed_ms=elapsed_ms,
        http_status=resp.status_code,
        curl_command=curl_command,
    )


def build_curl_probe_commands_from_url(url: str, timeout_seconds: int) -> str:
    return (
        f'curl -sS -o /dev/null -w "%{{http_code}} %{{time_total}}\\n" '
        f'--connect-timeout 10 -m {timeout_seconds} '
        f'-u "$ATLAS_USER:$ATLAS_PASS" -H "Accept: application/json" "{url}"'
    )


def diagnose_atlas_connectivity(
    config: ServerConfig,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    """Run lightweight Atlas/Knox connectivity probes and return structured diagnostics."""
    checks: List[Dict[str, Any]] = []
    recommendations: List[str] = []

    config_check = _check_config(config)
    checks.append(config_check)
    if config_check["status"] == "failed":
        recs = [str(config_check["recommendation"])] if config_check.get("recommendation") else []
        return {
            "overall": "failed",
            "summary": "Atlas connectivity checks failed. Review individual check messages and recommendations.",
            "timeout_seconds": config.timeout_seconds,
            "checks": checks,
            "curl_commands": [],
            "recommendations": recs,
        }

    if config_check.get("recommendation"):
        recommendations.append(str(config_check["recommendation"]))

    active_session = session or AtlasAuthFactory(
        user=config.atlas_user,
        password=config.atlas_password,
        verify=config.build_verify(),
    ).build_session()

    api_root = config.build_atlas_api_root()
    timeout_seconds = config.timeout_seconds
    probes = [
        ("admin_status", f"{api_root}/admin/status"),
        ("admin_version", f"{api_root}/admin/version"),
        ("v2_search_basic", f"{api_root}/v2/search/basic?query=*&limit=1"),
    ]

    for name, url in probes:
        result = _probe_get(active_session, url, name=name, timeout_seconds=timeout_seconds)
        checks.append(result)
        if result["status"] == "timeout":
            recommendations.extend(_timeout_recommendations(timeout_seconds))
        elif result.get("recommendation"):
            recommendations.append(str(result["recommendation"]))

    return _finalize_report(checks, config, recommendations)


def _finalize_report(
    checks: List[Mapping[str, Any]],
    config: ServerConfig,
    recommendations: List[str],
) -> Dict[str, Any]:
    statuses = [str(check["status"]) for check in checks]
    if any(status == "timeout" for status in statuses):
        overall = "timeout"
        summary = "One or more Atlas endpoints timed out. Use the curl commands below to reproduce outside MCP."
    elif any(status == "failed" for status in statuses):
        overall = "failed"
        summary = "Atlas connectivity checks failed. Review individual check messages and recommendations."
    elif any(status == "warning" for status in statuses):
        overall = "warning"
        summary = "Connected to Atlas, but configuration warnings were detected."
    else:
        overall = "ok"
        summary = "All Atlas connectivity checks passed."

    unique_recommendations = list(dict.fromkeys(recommendations))
    return {
        "overall": overall,
        "summary": summary,
        "timeout_seconds": config.timeout_seconds,
        "checks": checks,
        "curl_commands": build_curl_probe_commands(config),
        "recommendations": unique_recommendations,
    }


def main() -> None:
    config = ServerConfig()
    report = diagnose_atlas_connectivity(config)
    print(json.dumps(report, indent=2))
    if report["overall"] not in {"ok", "warning"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
