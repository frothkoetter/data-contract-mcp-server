from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import anyio

from .auth import AtlasAuthFactory
from .client import AtlasClient
from .config import ServerConfig
from .data_contracts import parse_quality_rules, parse_table_bindings

try:
    from mcp.server import FastMCP
except Exception as e:
    raise RuntimeError("The 'mcp' package is required. Install with: pip install mcp") from e


def _redact(obj: Any, max_items: int = 200) -> Any:
    """Redact sensitive keys and truncate large lists for LLM context."""
    _SENSITIVE = {"password", "passcode", "token", "secret", "passwd"}
    if isinstance(obj, dict):
        return {
            k: "***REDACTED***" if k.lower() in _SENSITIVE else _redact(v, max_items)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        if len(obj) > max_items:
            return [_redact(x, max_items) for x in obj[:max_items]] + [
                {"truncated": True, "omitted_count": len(obj) - max_items}
            ]
        return [_redact(x, max_items) for x in obj]
    return obj


def build_client(config: ServerConfig) -> AtlasClient:
    verify = config.build_verify()
    base_url = config.build_atlas_base()
    auth = AtlasAuthFactory(
        user=config.atlas_user,
        password=config.atlas_password,
        knox_token=config.knox_token,
        knox_cookie=config.knox_cookie,
        verify=verify,
    )
    session = auth.build_session()
    return AtlasClient(base_url, session, timeout_seconds=config.timeout_seconds)


def create_server(atlas: AtlasClient) -> FastMCP:
    app = FastMCP("atlas-mcp-server")

    # ── Admin / Status ─────────────────────────────────────────────────────

    @app.tool()
    async def get_atlas_status() -> Dict[str, Any]:
        """Get Apache Atlas server status and health information."""
        return _redact(atlas.get_status())

    @app.tool()
    async def get_atlas_metrics() -> Dict[str, Any]:
        """Get Apache Atlas metrics (entity counts by type, tag counts, etc.)."""
        return _redact(atlas.get_metrics())

    @app.tool()
    async def get_atlas_version() -> Dict[str, Any]:
        """Get Apache Atlas version information."""
        return _redact(atlas.get_version())

    # ── Search ─────────────────────────────────────────────────────────────

    @app.tool()
    async def search_entities(
        query: str = "*",
        type_name: Optional[str] = None,
        classification: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
        exclude_deleted: bool = True,
    ) -> Dict[str, Any]:
        """Search Atlas entities using basic search.

        Args:
            query: Search string. Use '*' to match all entities.
            type_name: Filter by entity type (e.g. 'hive_table', 'hdfs_path', 'kafka_topic').
            classification: Filter by classification/tag name.
            limit: Maximum results to return (default 25, max 1000).
            offset: Pagination offset.
            exclude_deleted: Whether to exclude deleted entities (default true).

        Returns list of matching entities with their GUIDs, names, and types.
        """
        return _redact(
            atlas.search_basic(
                query=query,
                type_name=type_name,
                classification=classification,
                limit=limit,
                offset=offset,
                exclude_deleted=exclude_deleted,
            )
        )

    @app.tool()
    async def fulltext_search(
        query: str,
        limit: int = 25,
        offset: int = 0,
        exclude_deleted: bool = True,
    ) -> Dict[str, Any]:
        """Full-text search across all Atlas entities and their attributes.

        More comprehensive than basic search — searches attribute values, descriptions,
        and comments. Slower than basic search for large catalogs.

        Args:
            query: Free-text query string.
            limit: Maximum results (default 25).
            offset: Pagination offset.
            exclude_deleted: Exclude deleted entities (default true).
        """
        return _redact(atlas.search_fulltext(query, limit=limit, offset=offset, exclude_deleted=exclude_deleted))

    @app.tool()
    async def dsl_search(
        query: str,
        limit: int = 25,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Search using Atlas DSL (Domain Specific Language) for precise queries.

        Atlas DSL examples:
          - 'hive_table'                          → all Hive tables
          - 'hive_table where name="sales"'       → Hive table named "sales"
          - 'hive_table where db.name="default"'  → tables in the default database
          - 'Column where dataType="string"'      → all string columns
          - 'hive_table where createTime > "2024-01-01"' → recently created tables
          - 'DataSet where owner="alice"'         → assets owned by alice

        Args:
            query: Atlas DSL query string.
            limit: Maximum results (default 25).
            offset: Pagination offset.
        """
        return _redact(atlas.search_dsl(query, limit=limit, offset=offset))

    @app.tool()
    async def search_by_classification(
        classification: str,
        entity_type: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Find all entities that have a specific classification (tag) applied.

        Useful for discovering all PII data, sensitive assets, or any custom-tagged entities.

        Args:
            classification: Classification/tag name (e.g. 'PII', 'Confidential', 'Sensitive').
            entity_type: Optionally narrow results to a specific entity type.
            limit: Maximum results (default 25).
            offset: Pagination offset.
        """
        return _redact(
            atlas.search_by_classification(
                classification=classification,
                entity_type=entity_type,
                limit=limit,
                offset=offset,
            )
        )

    # ── Entity ─────────────────────────────────────────────────────────────

    @app.tool()
    async def get_entity(
        guid: str,
        ignore_relationships: bool = False,
    ) -> Dict[str, Any]:
        """Get full details of an Atlas entity by its GUID.

        Returns all attributes, classifications, labels, and optionally relationships.

        Args:
            guid: The entity GUID (obtained from search results).
            ignore_relationships: If true, skip fetching relationship details (faster).
        """
        return _redact(atlas.get_entity_by_guid(guid, ignore_relationships=ignore_relationships))

    @app.tool()
    async def get_entity_by_attribute(
        type_name: str,
        attr_name: str,
        attr_value: str,
    ) -> Dict[str, Any]:
        """Get an entity by its unique attribute value instead of GUID.

        Useful when you know the qualified name or other unique attribute.

        Args:
            type_name: Entity type name (e.g. 'hive_table').
            attr_name: Unique attribute name — typically 'qualifiedName'.
            attr_value: The attribute value (e.g. 'default.sales_data@cluster1').

        Example: get_entity_by_attribute('hive_table', 'qualifiedName', 'default.orders@mycluster')
        """
        return _redact(atlas.get_entity_by_attribute(type_name, attr_name, attr_value))

    @app.tool()
    async def get_entity_classifications(guid: str) -> Dict[str, Any]:
        """Get all classifications (tags) applied to an entity.

        Args:
            guid: The entity GUID.
        """
        return _redact(atlas.get_entity_classifications(guid))

    @app.tool()
    async def get_entity_labels(guid: str) -> Dict[str, Any]:
        """Get all labels applied to an entity.

        Labels are free-form strings, unlike classifications which have a defined schema.

        Args:
            guid: The entity GUID.
        """
        return _redact(atlas.get_entity_labels(guid))

    @app.tool()
    async def get_entity_audit(
        guid: str,
        count: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get the audit history of changes made to an entity.

        Shows who changed what attributes, when classifications were added/removed, etc.

        Args:
            guid: The entity GUID.
            count: Number of audit entries to return (default 50, max 1000).
        """
        return _redact(atlas.get_entity_audit(guid, count=count))

    @app.tool()
    async def add_classification_to_entity(
        guid: str,
        classification_name: str,
        attributes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply a classification (tag) to an entity. **WRITE OPERATION**

        Args:
            guid: The entity GUID.
            classification_name: Name of the classification type to apply.
            attributes: Optional JSON string of classification attribute key-value pairs.
                        Example: '{"expiry_date": "2025-12-31"}'
        """
        import json
        attrs = json.loads(attributes) if attributes else {}
        payload = [{"typeName": classification_name, "attributes": attrs}]
        atlas.add_classification(guid, payload)
        return {"status": "ok", "guid": guid, "classification": classification_name}

    @app.tool()
    async def remove_classification_from_entity(
        guid: str,
        classification_name: str,
    ) -> Dict[str, Any]:
        """Remove a classification (tag) from an entity. **WRITE OPERATION**

        Args:
            guid: The entity GUID.
            classification_name: Name of the classification to remove.
        """
        atlas.remove_classification(guid, classification_name)
        return {"status": "ok", "guid": guid, "removed_classification": classification_name}

    @app.tool()
    async def add_labels_to_entity(
        guid: str,
        labels: str,
    ) -> Dict[str, Any]:
        """Add labels to an entity. **WRITE OPERATION**

        Labels are free-form strings for lightweight tagging.

        Args:
            guid: The entity GUID.
            labels: Comma-separated list of labels (e.g. 'finance,approved,v2').
        """
        label_list = [lbl.strip() for lbl in labels.split(",") if lbl.strip()]
        atlas.add_labels(guid, label_list)
        return {"status": "ok", "guid": guid, "added_labels": label_list}

    # ── Lineage ────────────────────────────────────────────────────────────

    @app.tool()
    async def get_lineage(
        guid: str,
        direction: str = "BOTH",
        depth: int = 3,
    ) -> Dict[str, Any]:
        """Get the data lineage graph for an entity.

        Returns the upstream (INPUT) and/or downstream (OUTPUT) lineage, showing
        which datasets feed into this entity and which datasets it feeds into.

        Args:
            guid: The entity GUID.
            direction: 'INPUT' (upstream), 'OUTPUT' (downstream), or 'BOTH' (default).
            depth: How many hops to traverse (default 3). Use 1 for direct lineage only.

        Returns a graph with 'guidEntityMap' (entity details) and 'relations' (edges).
        """
        if direction not in ("INPUT", "OUTPUT", "BOTH"):
            return {"error": f"Invalid direction '{direction}'. Use INPUT, OUTPUT, or BOTH."}
        return _redact(atlas.get_lineage_by_guid(guid, direction=direction, depth=depth))

    @app.tool()
    async def get_lineage_by_attribute(
        type_name: str,
        attr_name: str,
        attr_value: str,
        direction: str = "BOTH",
        depth: int = 3,
    ) -> Dict[str, Any]:
        """Get data lineage using a unique attribute instead of GUID.

        Args:
            type_name: Entity type name (e.g. 'hive_table').
            attr_name: Unique attribute name — typically 'qualifiedName'.
            attr_value: The attribute value.
            direction: 'INPUT', 'OUTPUT', or 'BOTH' (default).
            depth: Lineage traversal depth (default 3).
        """
        if direction not in ("INPUT", "OUTPUT", "BOTH"):
            return {"error": f"Invalid direction '{direction}'. Use INPUT, OUTPUT, or BOTH."}
        return _redact(
            atlas.get_lineage_by_attribute(
                type_name, attr_name, attr_value, direction=direction, depth=depth
            )
        )

    # ── Types ──────────────────────────────────────────────────────────────

    @app.tool()
    async def list_entity_types() -> Dict[str, Any]:
        """List all registered entity type names in the Atlas catalog.

        Returns a summary of entity type names and counts. Use get_entity_type_definition()
        to see the full attribute schema for a specific type.

        Common CDP types include: hive_table, hive_column, hive_db, hdfs_path,
        kafka_topic, hbase_table, spark_process, impala_column_lineage, etc.
        """
        headers = atlas.list_type_names(type_category="ENTITY")
        return _redact(headers)

    @app.tool()
    async def list_classification_types() -> Dict[str, Any]:
        """List all registered classification (tag) type names in Atlas.

        Classifications include built-in types like PII, Sensitive, Confidential,
        plus any custom tags defined in your environment.
        """
        headers = atlas.list_type_names(type_category="CLASSIFICATION")
        return _redact(headers)

    @app.tool()
    async def get_entity_type_definition(type_name: str) -> Dict[str, Any]:
        """Get the full attribute schema for an entity type.

        Shows all attributes, their data types, whether they are required,
        and their cardinality. Useful for understanding what fields an entity has
        before searching or filtering by them.

        Args:
            type_name: Entity type name (e.g. 'hive_table', 'kafka_topic').
        """
        return _redact(atlas.get_entity_type_def(type_name))

    @app.tool()
    async def get_classification_definition(classification_name: str) -> Dict[str, Any]:
        """Get the attribute schema for a classification (tag) type.

        Args:
            classification_name: Classification type name (e.g. 'PII', 'Confidential').
        """
        return _redact(atlas.get_classification_type_def(classification_name))

    # ── Glossary ───────────────────────────────────────────────────────────

    @app.tool()
    async def list_glossaries() -> Any:
        """List all business glossaries defined in Atlas.

        Glossaries contain business terms that can be linked to data assets
        to provide business context and definitions.
        """
        return _redact(atlas.list_glossaries())

    @app.tool()
    async def list_glossary_terms(
        glossary_guid: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Any:
        """List glossary terms, optionally filtered to a specific glossary.

        Args:
            glossary_guid: GUID of the glossary to list terms from. If omitted, lists all terms.
            limit: Maximum terms to return (default 100).
            offset: Pagination offset.
        """
        return _redact(atlas.list_glossary_terms(glossary_guid=glossary_guid, limit=limit, offset=offset))

    @app.tool()
    async def get_glossary_term(term_guid: str) -> Dict[str, Any]:
        """Get full details of a glossary term including its definition and linked entities.

        Args:
            term_guid: The GUID of the glossary term.
        """
        return _redact(atlas.get_glossary_term(term_guid))

    @app.tool()
    async def get_entities_for_glossary_term(
        term_guid: str,
        limit: int = 25,
        offset: int = 0,
    ) -> Any:
        """Find all data assets (entities) associated with a glossary term.

        Args:
            term_guid: The GUID of the glossary term.
            limit: Maximum results (default 25).
            offset: Pagination offset.
        """
        return _redact(atlas.get_entities_for_term(term_guid, limit=limit, offset=offset))

    # ── Relationship ───────────────────────────────────────────────────────

    @app.tool()
    async def get_relationship(guid: str) -> Dict[str, Any]:
        """Get details of a relationship between two Atlas entities.

        Args:
            guid: The relationship GUID (found in entity relationship attributes).
        """
        return _redact(atlas.get_relationship_by_guid(guid))

    # ── Bulk entity fetch ──────────────────────────────────────────────────

    @app.tool()
    async def get_entities_bulk(guids: str) -> Dict[str, Any]:
        """Fetch multiple entities by their GUIDs in a single call.

        Args:
            guids: Comma-separated list of entity GUIDs.
                   Example: 'abc-123,def-456,ghi-789'
        """
        guid_list = [g.strip() for g in guids.split(",") if g.strip()]
        if not guid_list:
            return {"error": "No GUIDs provided"}
        return _redact(atlas.get_entities_by_guids(guid_list))

    # ── Data contracts ─────────────────────────────────────────────────────

    @app.tool()
    async def ensure_data_contract_typedef() -> Dict[str, Any]:
        """Register the data_contract entity and relationship typedefs in Atlas. **WRITE OPERATION**

        Idempotent: returns status 'exists' if the type is already registered, otherwise creates it.
        Must be run once before using the other data contract tools.
        """
        return _redact(atlas.ensure_data_contract_typedef())

    @app.tool()
    async def get_data_contract(
        contract_id: Optional[str] = None,
        version: Optional[str] = None,
        qualified_name: Optional[str] = None,
        ignore_relationships: bool = False,
    ) -> Dict[str, Any]:
        """Get a data contract by id/version or qualifiedName, including bound tables.

        Args:
            contract_id: Contract id (required unless qualified_name is given).
            version: Contract version (required unless qualified_name is given).
            qualified_name: Atlas qualifiedName (defaults to '{contract_id}@{version}').
            ignore_relationships: If true, skip assigned_datasets relationship details.
        """
        return _redact(
            atlas.get_data_contract(
                contract_id=contract_id,
                version=version,
                qualified_name=qualified_name,
                ignore_relationships=ignore_relationships,
            )
        )

    @app.tool()
    async def search_data_contracts(
        query: str = "*",
        status: Optional[str] = None,
        contract_id: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
        exclude_deleted: bool = True,
    ) -> Dict[str, Any]:
        """Search data_contract entities in Atlas.

        Uses DSL when status or contract_id filters are provided; otherwise basic search.

        Args:
            query: Free-text search string. Use '*' to list all contracts.
            status: Filter by contract status (e.g. 'active', 'broken', 'draft').
            contract_id: Filter by contract id.
            limit: Maximum results (default 25).
            offset: Pagination offset.
            exclude_deleted: Exclude deleted entities (default true).
        """
        return _redact(
            atlas.search_data_contracts(
                query=query,
                status=status,
                contract_id=contract_id,
                limit=limit,
                offset=offset,
                exclude_deleted=exclude_deleted,
            )
        )

    @app.tool()
    async def create_data_contract(
        contract_id: str,
        version: str,
        status: str = "draft",
        quality_rules: Optional[str] = None,
        qualified_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create or update a data_contract entity in Atlas. **WRITE OPERATION**

        Idempotent via qualifiedName (defaults to '{contract_id}@{version}').

        Args:
            contract_id: Unique contract identifier (ODCS contract id).
            version: Contract version string.
            status: Contract status (e.g. 'draft', 'active', 'broken').
            quality_rules: Optional comma-separated rules or JSON array string.
            qualified_name: Optional override for the Atlas qualifiedName.
        """
        rules = parse_quality_rules(quality_rules)
        return _redact(
            atlas.create_data_contract(
                contract_id=contract_id,
                version=version,
                status=status,
                quality_rules=rules or None,
                qualified_name=qualified_name,
            )
        )

    @app.tool()
    async def update_data_contract_status(
        status: str,
        contract_id: Optional[str] = None,
        version: Optional[str] = None,
        qualified_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update the status of a data contract (e.g. active or broken). **WRITE OPERATION**

        Args:
            status: New status value (e.g. 'active', 'broken').
            contract_id: Contract id (required unless qualified_name is given).
            version: Contract version (required unless qualified_name is given).
            qualified_name: Atlas qualifiedName (defaults to '{contract_id}@{version}').
        """
        return _redact(
            atlas.update_data_contract_status(
                status=status,
                contract_id=contract_id,
                version=version,
                qualified_name=qualified_name,
            )
        )

    @app.tool()
    async def bind_contract_to_table(
        table_qualified_names: str,
        contract_id: Optional[str] = None,
        version: Optional[str] = None,
        qualified_name: Optional[str] = None,
        table_type: str = "hive_table",
    ) -> Dict[str, Any]:
        """Bind a data contract to one or more tables via datacontract_dataset_assignment. **WRITE OPERATION**

        Args:
            table_qualified_names: Comma-separated Atlas qualifiedNames of target tables.
            contract_id: Contract id (required unless qualified_name is given).
            version: Contract version (required unless qualified_name is given).
            qualified_name: Atlas qualifiedName of the contract.
            table_type: Entity type of the tables — 'hive_table' or 'iceberg_table'.
        """
        bindings = parse_table_bindings(table_qualified_names, table_type=table_type)
        return _redact(
            atlas.bind_contract_to_tables(
                table_qualified_names=bindings,
                contract_id=contract_id,
                version=version,
                qualified_name=qualified_name,
            )
        )

    @app.tool()
    async def delete_data_contract(
        contract_id: Optional[str] = None,
        version: Optional[str] = None,
        qualified_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Permanently delete a specific data contract version. **WRITE OPERATION**

        Performs a hard delete (purge=true) of the contract entity identified by qualifiedName.

        Args:
            contract_id: Contract id (required unless qualified_name is given).
            version: Contract version (required unless qualified_name is given).
            qualified_name: Atlas qualifiedName (defaults to '{contract_id}@{version}').
        """
        return _redact(
            atlas.delete_data_contract(
                contract_id=contract_id,
                version=version,
                qualified_name=qualified_name,
            )
        )

    return app


async def _run_stdio() -> None:
    config = ServerConfig()
    atlas = build_client(config)
    server = create_server(atlas)
    await server.run_stdio_async()


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if transport != "stdio":
        config = ServerConfig()
        atlas = build_client(config)
        server = create_server(atlas)
        server.run(transport=transport)
        return
    anyio.run(_run_stdio)


if __name__ == "__main__":
    main()
