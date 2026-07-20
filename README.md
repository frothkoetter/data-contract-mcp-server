# Data Contract MCP Server

Model Context Protocol server for managing ODCS data contracts in Apache Atlas, with full read access to the Atlas data catalog via Apache Knox.

## Features

- **Knox authentication** — supports JWT tokens, raw cookies, and Basic Auth for CDP deployments
- **ODCS Hybrid v2.3 contracts** — schema, quality, SLA, and enforcement policies stored as first-class Atlas attributes
- **Read-mostly** — safe exploration of entities, lineage, types, and glossaries; a small set of write tools for tagging and labeling
- **Automatic retries** — exponential backoff on transient errors

### MCP Tools

**Admin / Status**
- `get_atlas_status()` — Server health information
- `get_atlas_metrics()` — Entity and tag counts by type
- `get_atlas_version()` — Atlas version
- `diagnose_atlas_connectivity()` — Structured connectivity probes with curl commands and timeout diagnostics

**Search**
- `search_entities(query, type_name?, classification?, limit, offset, exclude_deleted)` — Basic search; use `'*'` to browse all
- `fulltext_search(query, limit, offset, exclude_deleted)` — Full-text search across attribute values and descriptions
- `dsl_search(query, limit, offset)` — Atlas DSL queries (e.g. `hive_table where db.name="default"`)
- `search_by_classification(classification, entity_type?, limit, offset)` — Find all entities with a given tag (e.g. `PII`)

**Entity**
- `get_entity(guid, ignore_relationships?)` — Full entity details including classifications and relationships
- `get_entity_by_attribute(type_name, attr_name, attr_value)` — Lookup by `qualifiedName` or other unique attribute
- `get_entity_classifications(guid)` — Tags applied to an entity
- `get_entity_labels(guid)` — Free-form labels on an entity
- `get_entity_audit(guid, count)` — Audit history of attribute and classification changes
- `get_entities_bulk(guids)` — Fetch multiple entities in one call (comma-separated GUIDs)

**Lineage**
- `get_lineage(guid, direction, depth)` — Data lineage graph (`INPUT`, `OUTPUT`, or `BOTH`)
- `get_lineage_by_attribute(type_name, attr_name, attr_value, direction, depth)` — Lineage without a GUID

**Types**
- `list_entity_types()` — All registered entity type names
- `list_classification_types()` — All classification (tag) type names
- `get_entity_type_definition(type_name)` — Full attribute schema for an entity type
- `get_classification_definition(classification_name)` — Attribute schema for a classification type

**Glossary**
- `list_glossaries()` — All business glossaries
- `list_glossary_terms(glossary_guid?, limit, offset)` — Terms in a glossary (or all terms)
- `get_glossary_term(term_guid)` — Term definition and linked entities
- `get_entities_for_glossary_term(term_guid, limit, offset)` — Data assets linked to a term

**Relationship**
- `get_relationship(guid)` — Details of an entity-to-entity relationship

**Write operations**
- `add_classification_to_entity(guid, classification_name, attributes?)` — Apply a tag to an entity
- `remove_classification_from_entity(guid, classification_name)` — Remove a tag from an entity
- `add_labels_to_entity(guid, labels)` — Add free-form labels (comma-separated)

**Data contracts**
- `ensure_data_contract_typedef()` — Register or upgrade the `data_contract` entity (v2.3), struct types, and `datacontract_dataset_assignment` relationship in Atlas (run once)
- `get_data_contract(contract_id?, version?, qualified_name?, ignore_relationships?)` — Fetch a contract with bound tables
- `search_data_contracts(query?, status?, contract_id?, limit, offset, exclude_deleted)` — Search or list contracts
- `create_data_contract(...)` — Create or update a contract (idempotent via qualifiedName); see [Data contract model](#data-contract-model) below
- `update_data_contract_status(status, contract_id?, version?, qualified_name?)` — Set contract status (e.g. `active`, `broken`)
- `bind_contract_to_table(table_qualified_names, contract_id?, version?, qualified_name?, table_type?)` — Link contract to hive/iceberg tables
- `delete_data_contract(contract_id?, version?, qualified_name?)` — Hard-delete a specific contract version

## Data contract model

Atlas entity type `data_contract` (Hybrid v2.3) stores ODCS contract metadata alongside derived search fields.

| Field | Description |
|-------|-------------|
| `contractId`, `version`, `status` | Identity and lifecycle (`draft`, `active`, `broken`) |
| `name`, `domain`, `data_product`, `tenant` | ODCS fundamentals |
| `description_purpose`, `description_limitations` | Usage context |
| `tags`, `consumer` | Labels and consumers (roles, groups, persons) |
| `quality_rules` | Legacy plain-text rules |
| `quality` | Structured ODCS quality rules (`metric`, `threshold`, `severity`, `enforcement_policy`, …) |
| `sla_properties` | SLA properties (freshness, frequency, …) |
| `schema_objects`, `schema_properties` | Schema with flattened columns for Atlas |
| `enforcement_policies` | Violation handling policies (alert, block, quarantine, escalate, …) |
| `enforcement_mode` | `monitor` \| `enforce` \| `dry_run` |
| `enforcement_default_action` | Fallback action when no policy matches |
| `auto_mark_broken_on_critical` | Flag for auto-setting `status=broken` on critical violations |
| `ranger_service` | Default Ranger service (e.g. `cm_hive`) for access-block policies |
| `odcs_document` | Full ODCS YAML/JSON blob |

**Enforcement is declarative.** Policies are stored in Atlas; an external orchestrator (CDQ job, NiFi flow, custom service) reads them and executes actions such as Ranger deny policies, alerts, or quarantine routing. This MCP server does not call Ranger directly.

### `create_data_contract` parameters

```
create_data_contract(
  contract_id,                          # required
  version,                              # required
  status?,                              # default: draft
  quality_rules?,                       # comma-separated, JSON array, or list
  qualified_name?,                      # default: {contract_id}@{version}
  name?, domain?, data_product?, tenant?,
  description_purpose?, description_limitations?,
  tags?, consumer?,                     # comma-separated, JSON array, or list
  sla_default_element?,
  odcs_document?,                       # full ODCS YAML/JSON string
  schema_objects?,                      # list or JSON string
  quality?,                             # structured ODCS quality rules
  sla_properties?,                      # structured SLA properties
  enforcement_policies?,                # list or JSON string
  enforcement_default_action?,          # alert, block_access, quarantine, ...
  enforcement_mode?,                    # monitor | enforce | dry_run
  auto_mark_broken_on_critical?,
  ranger_service?,                      # e.g. cm_hive
)
```

Structured array fields (`schema_objects`, `quality`, `sla_properties`, `quality_rules`, `tags`, `consumer`, `enforcement_policies`) accept either a **JSON array string** or a **native list** (for agent callers).

### Example: contract with quality and enforcement

```json
{
  "contract_id": "orders-contract",
  "version": "1.0",
  "status": "active",
  "name": "Orders Data Contract",
  "domain": "sales",
  "data_product": "orders",
  "consumer": ["group:analysts", "group:risk-analytics"],
  "enforcement_mode": "enforce",
  "enforcement_default_action": "alert",
  "auto_mark_broken_on_critical": true,
  "ranger_service": "cm_hive",
  "schema_objects": [{
    "name": "orders",
    "logicalType": "object",
    "properties": [
      {"name": "id", "logicalType": "string", "primaryKey": true},
      {"name": "customer_email", "logicalType": "string"},
      {"name": "updated_at", "logicalType": "date"}
    ]
  }],
  "quality": [{
    "metric": "freshness",
    "threshold": "24",
    "unit": "h",
    "element": "orders.updated_at",
    "severity": "critical",
    "enforcement_policy": "freshness-block"
  }],
  "sla_properties": [{"property": "freshness", "value": "24", "unit": "h"}],
  "enforcement_policies": [{
    "name": "freshness-block",
    "trigger": "quality_violation",
    "action": "block_and_alert",
    "rule_filter": "freshness",
    "severity": "critical",
    "notify_channel": "slack",
    "notify_targets": ["#data-alerts"],
    "ranger_policy_template": "deny_read"
  }]
}
```

### Example: ODCS column completeness check

Pass column-level rules in the **`quality`** array (not `quality_rules`). Link enforcement via
`enforcement_policy` (rule reference) and a matching entry in `enforcement_policies`:

```json
{
  "contract_id": "mart-portfolio-risk",
  "version": "1.0",
  "status": "active",
  "name": "Mart Portfolio Risk Contract",
  "domain": "buba_risk_analytics",
  "ranger_service": "cm_hive",
  "schema_objects": [{
    "name": "mart_portfolio_risk_summary",
    "logicalType": "object",
    "properties": [
      {"name": "reporting_bank_bic", "logicalType": "string", "required": true}
    ]
  }],
  "quality": [{
    "name": "DQ_NOT_NULL_reporting_bank_bic",
    "description": "Ensure reporting_bank_bic is not null for all records.",
    "rule_type": "completeness",
    "metric": "not_null_count",
    "query": "SELECT COUNT(*) FROM mart_portfolio_risk_summary WHERE reporting_bank_bic IS NULL",
    "threshold": 0,
    "severity": "critical",
    "enforcement_policy": "block_access_on_violation",
    "business_impact": "Null BIC codes prevent correct bank-level aggregation and reporting.",
    "element": "reporting_bank_bic"
  }],
  "enforcement_policies": [{
    "name": "block_access_on_violation",
    "trigger": "quality_violation",
    "action": "block_access",
    "rule_filter": "DQ_NOT_NULL_reporting_bank_bic",
    "severity": "critical"
  }]
}
```

CamelCase ODCS keys (`ruleType`, `businessImpact`, `enforcementPolicy`) are also accepted.

### Enforcement policy actions

| Action | Intended runtime behavior |
|--------|---------------------------|
| `log_only` | Record violation only |
| `alert` | Notify via configured channel |
| `mark_broken` | Set contract status to `broken` |
| `block_access` | Apply Ranger deny policy on bound tables |
| `quarantine` | Route failing rows to `quarantine_target` table |
| `escalate` | Alert and escalate after `escalate_after_minutes` |
| `block_and_alert` | Ranger block + notification |
| `quarantine_and_alert` | Quarantine + notification |

### Ranger column masking (external)

Column masking and hashing use Ranger **masking policies** (`policyType: 1`), separate from access/deny policies. Map contract `schema_properties` and `consumer` groups to Ranger `dataMaskPolicyItems` with `dataMaskType` values such as `MASK_HASH`, `MASK_SHOW_LAST_4`, or `MASK_NULL`. See Apache Ranger masking docs for REST API details; execution is handled outside this MCP server.

## Setup

### Option 1: Claude Desktop (Local)

1. **Clone and install:**
   ```bash
   git clone <repo-url>
   cd data-contract-mcp-server
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```

2. **Configure Claude Desktop** — edit `~/Library/Application Support/Claude/claude_desktop_config.json`:
   ```json
   {
     "mcpServers": {
       "data-contract-mcp-server": {
         "command": "/FULL/PATH/TO/data-contract-mcp-server/.venv/bin/python",
         "args": ["-m", "data_contract_mcp_server.server"],
         "env": {
           "MCP_TRANSPORT": "stdio",
           "ATLAS_GATEWAY_URL": "https://<host>/<topology>/cdp-proxy-api/atlas/api/atlas/",
           "KNOX_TOKEN": "<your_knox_jwt_token>"
         }
       }
     }
   }
   ```

3. **Restart Claude Desktop** and start asking questions about your data catalog.

### Option 2: uvx (Cloudera Agent Studio)

```json
{
  "mcpServers": {
    "data-contract-mcp-server": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/frothkoetter/data-contract-mcp-server.git@datacontract",
        "run-server"
      ],
      "env": {
        "ATLAS_GATEWAY_URL": "https://<host>/<topology>/cdp-proxy-api/atlas/api/atlas/",
        "ATLAS_USER": "<your_username>",
        "ATLAS_PASS": "<your_password>"
      }
    }
  }
}
```

## Configuration

All configuration is done via environment variables.

### Connection

| Variable | Required | Description |
|----------|----------|-------------|
| `ATLAS_GATEWAY_URL` | Yes | Full CDP Knox Atlas API URL (e.g. `https://<host>/<topology>/cdp-proxy-api/atlas/api/atlas/`). |

### Authentication (pick one)

| Variable | Priority | Description |
|----------|----------|-------------|
| `KNOX_COOKIE` | Highest | Raw cookie string (e.g. `hadoop-jwt=<token>`) |
| `KNOX_TOKEN` | Medium | Knox JWT token — sent as `hadoop-jwt` cookie |
| `ATLAS_USER` + `ATLAS_PASS` | Lowest | Basic auth credentials |

### TLS / HTTP

| Variable | Default | Description |
|----------|---------|-------------|
| `ATLAS_VERIFY_SSL` | `true` | Set `false` to disable certificate verification |
| `ATLAS_CA_BUNDLE` | — | Path to a CA certificate bundle |
| `HTTP_TIMEOUT_SECONDS` | `30` | Request timeout in seconds |
| `HTTP_MAX_RETRIES` | `3` | Maximum retry attempts on transient errors |

### Server Transport

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_TRANSPORT` | `stdio` | Transport mode: `stdio`, `http`, or `sse` |
| `MCP_HOST` | `127.0.0.1` | Bind address (for `http`/`sse` modes) |
| `MCP_PORT` | `3030` | Port (for `http`/`sse` modes) |

### CDP URL pattern

The `ATLAS_GATEWAY_URL` for a CDP Flow Management DataHub is the full Atlas API path through Knox, for example:

```
https://<cluster-host>/<topology>/cdp-proxy-api/atlas/api/atlas/
```

A trailing slash is optional.

## Troubleshooting Atlas timeouts

When MCP tools fail with connection or read timeouts, run connectivity diagnostics before
changing contract or typedef code.

### Option 1: MCP tool

Ask the agent to call `diagnose_atlas_connectivity()`. The response includes:

- `overall`: `ok`, `warning`, `timeout`, or `failed`
- `checks`: per-endpoint status, elapsed ms, HTTP code, and message
- `curl_commands`: equivalent shell probes (credentials via `$ATLAS_USER` / `$ATLAS_PASS`)
- `recommendations`: remediation hints (VPN, timeout, URL format, TLS, auth)

### Option 2: curl script (outside MCP)

```bash
export ATLAS_GATEWAY_URL="https://<host>/<topology>/cdp-proxy-api/atlas/api/atlas/"
export ATLAS_USER="your_user"
export ATLAS_PASS="your_password"
# optional for sandboxes: export ATLAS_VERIFY_SSL=false
# optional: export HTTP_TIMEOUT_SECONDS=60

chmod +x scripts/curl_atlas_diagnostics.sh
./scripts/curl_atlas_diagnostics.sh
```

The script probes three endpoints:

1. `{ATLAS_GATEWAY_URL}/admin/status` — Knox/Atlas health (no `/v2`)
2. `{ATLAS_GATEWAY_URL}/admin/version` — version metadata
3. `{ATLAS_GATEWAY_URL}/v2/search/basic?query=*&limit=1` — v2 API smoke test

On **curl exit 28** (timeout) it prints diagnostics such as:

- Knox/Atlas unreachable or blocked by firewall/VPN
- Increase `HTTP_TIMEOUT_SECONDS`
- Verify the gateway URL path ends with `.../cdp-proxy-api/atlas/api/atlas/`

### Option 3: Python CLI

```bash
uv run python -m data_contract_mcp_server.diagnostics
```

Prints the same structured JSON report and exits non-zero on failure/timeout.

### Manual single-endpoint curl

```bash
curl -sS -w "\nHTTP %{http_code} total %{time_total}s\n" \
  --connect-timeout 10 -m "${HTTP_TIMEOUT_SECONDS:-30}" \
  -u "$ATLAS_USER:$ATLAS_PASS" \
  -H "Accept: application/json" \
  "${ATLAS_GATEWAY_URL%/}/admin/status"
```

If this times out but Ranger or other CDP APIs work, Atlas/Knox may be down or the URL path
may be wrong. A common mistake is a double `/v2/` segment — the gateway URL should **not**
include `/v2`; the client adds it for v2 REST calls.

## Example Queries

Once configured, you can ask Claude things like:

- "What entity types are registered in Atlas?"
- "Find all Hive tables in the default database"
- "Show me the lineage for table `default.orders@mycluster`"
- "Which entities are tagged as PII?"
- "What does the glossary term 'Customer ID' mean?"
- "Show me the audit history for entity guid abc-123"
- "Search for all Kafka topics containing 'events'"
- "Tag entity abc-123 as Confidential"
- "Register the data contract typedef in Atlas"
- "Create an ODCS data contract for orders with a freshness SLA and enforcement policy"
- "List all active data contracts"
- "Bind contract `orders-contract@1.0` to table `sales.orders@cluster`"

## License

Apache License 2.0
