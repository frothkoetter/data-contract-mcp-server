#!/usr/bin/env bash
# Probe Atlas/Knox connectivity with curl when MCP requests time out.
#
# Usage:
#   export ATLAS_GATEWAY_URL="https://<host>/<topology>/cdp-proxy-api/atlas/api/atlas/"
#   export ATLAS_USER="..."
#   export ATLAS_PASS="..."
#   # optional: export ATLAS_VERIFY_SSL=false
#   # optional: export HTTP_TIMEOUT_SECONDS=30
#   ./scripts/curl_atlas_diagnostics.sh
#
# Or load a project .env first:
#   set -a; source .env; set +a; ./scripts/curl_atlas_diagnostics.sh

set -euo pipefail

TIMEOUT="${HTTP_TIMEOUT_SECONDS:-30}"
CONNECT_TIMEOUT=10
VERIFY_SSL="${ATLAS_VERIFY_SSL:-true}"

if [[ -z "${ATLAS_GATEWAY_URL:-}" ]]; then
  echo "ERROR: ATLAS_GATEWAY_URL is not set."
  echo "Example: https://<host>/<topology>/cdp-proxy-api/atlas/api/atlas/"
  exit 1
fi

if [[ -z "${ATLAS_USER:-}" || -z "${ATLAS_PASS:-}" ]]; then
  echo "ERROR: ATLAS_USER and ATLAS_PASS must be set."
  exit 1
fi

API_ROOT="${ATLAS_GATEWAY_URL%/}"
API_ROOT="${API_ROOT%/v2}"

CURL_TLS=()
if [[ "${VERIFY_SSL}" =~ ^(0|false|no)$ ]]; then
  CURL_TLS=(-k)
elif [[ -n "${ATLAS_CA_BUNDLE:-}" ]]; then
  CURL_TLS=(--cacert "${ATLAS_CA_BUNDLE}")
fi

probe() {
  local label="$1"
  local url="$2"
  local body_file
  body_file="$(mktemp)"
  local curl_cmd=(
    curl -sS
    "${CURL_TLS[@]}"
    -u "${ATLAS_USER}:${ATLAS_PASS}"
    -H "Accept: application/json"
    --connect-timeout "${CONNECT_TIMEOUT}"
    -m "${TIMEOUT}"
    -o "${body_file}"
    -w "HTTP %{http_code} total %{time_total}s connect %{time_connect}s\n"
    "${url}"
  )

  echo ""
  echo "=== ${label} ==="
  echo "URL: ${url}"
  echo "Command: ${curl_cmd[*]}"

  set +e
  output="$("${curl_cmd[@]}" 2>&1)"
  exit_code=$?
  set -e

  echo "${output}"

  if [[ ${exit_code} -eq 28 ]]; then
    echo "DIAGNOSIS: curl timed out (exit 28)."
    echo "  - Knox/Atlas may be down, unreachable, or blocked by firewall/VPN."
    echo "  - Try from a host inside the CDP network or increase HTTP_TIMEOUT_SECONDS (now ${TIMEOUT})."
    echo "  - Verify ATLAS_GATEWAY_URL ends with .../cdp-proxy-api/atlas/api/atlas/"
    return 28
  fi

  if [[ ${exit_code} -ne 0 ]]; then
    echo "DIAGNOSIS: curl failed (exit ${exit_code})."
    echo "  - Check DNS, TLS (ATLAS_CA_BUNDLE / ATLAS_VERIFY_SSL), and credentials."
    return "${exit_code}"
  fi

  http_code="$(echo "${output}" | awk '{print $2}')"
  if [[ "${http_code}" == "401" || "${http_code}" == "403" ]]; then
    echo "DIAGNOSIS: authentication/authorization rejected (HTTP ${http_code})."
    echo "  - Verify ATLAS_USER / ATLAS_PASS and Knox permissions."
    return 1
  fi

  if [[ "${http_code}" =~ ^5 ]]; then
    echo "DIAGNOSIS: server error (HTTP ${http_code}). Inspect Knox/Atlas logs."
    echo "Response preview:"
    head -c 400 "${body_file}" || true
    echo ""
    rm -f "${body_file}"
    return 1
  fi

  echo "OK: HTTP ${http_code}"
  echo "Response preview:"
  head -c 400 "${body_file}" || true
  echo ""
  rm -f "${body_file}"
  return 0
}

echo "Atlas curl diagnostics"
echo "API root: ${API_ROOT}"
echo "Timeout: connect ${CONNECT_TIMEOUT}s, max ${TIMEOUT}s"

failures=0
probe "Admin status" "${API_ROOT}/admin/status" || failures=$((failures + 1))
probe "Admin version" "${API_ROOT}/admin/version" || failures=$((failures + 1))
probe "v2 search smoke test" "${API_ROOT}/v2/search/basic?query=*&limit=1" || failures=$((failures + 1))

echo ""
if [[ ${failures} -eq 0 ]]; then
  echo "All probes succeeded."
  exit 0
fi

echo "${failures} probe(s) failed. Run: uv run python -m data_contract_mcp_server.diagnostics"
exit 1
