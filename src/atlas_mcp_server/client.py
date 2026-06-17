from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .data_contracts import (
    DATA_CONTRACT_TYPE,
    DATA_CONTRACT_TYPEDEF,
    build_qualified_name,
    parse_quality_rules,
    parse_table_bindings,
)


class AtlasError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, response_body: Optional[str] = None):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(message)

    def __str__(self) -> str:
        msg = super().__str__()
        if self.status_code:
            msg = f"[{self.status_code}] {msg}"
        if self.response_body:
            msg = f"{msg}\n\nAtlas API Response:\n{self.response_body}"
        return msg


_RETRYABLE = (AtlasError, requests.ConnectionError, requests.Timeout)


class AtlasClient:
    def __init__(self, base_url: str, session: requests.Session, timeout_seconds: int = 30):
        self.base_url = base_url.rstrip("/")
        self.session = session
        self.timeout = timeout_seconds

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        resp = self.session.get(self._url(path), params=params, timeout=self.timeout)
        if not resp.ok:
            raise AtlasError(f"GET {path} failed: {resp.reason}", resp.status_code, resp.text or "(empty)")
        return resp.json()

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _post(self, path: str, data: Any) -> Any:
        resp = self.session.post(self._url(path), json=data, timeout=self.timeout)
        if not resp.ok:
            raise AtlasError(f"POST {path} failed: {resp.reason}", resp.status_code, resp.text or "(empty)")
        return resp.json() if resp.content else {}

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _put(self, path: str, data: Any) -> Any:
        resp = self.session.put(self._url(path), json=data, timeout=self.timeout)
        if not resp.ok:
            raise AtlasError(f"PUT {path} failed: {resp.reason}", resp.status_code, resp.text or "(empty)")
        return resp.json() if resp.content else {}

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _delete(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        resp = self.session.delete(self._url(path), params=params, timeout=self.timeout)
        if not resp.ok:
            raise AtlasError(f"DELETE {path} failed: {resp.reason}", resp.status_code, resp.text or "(empty)")
        return resp.json() if resp.content else {}

    # ── Admin ──────────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        return self._get("admin/status")

    def get_metrics(self) -> Dict[str, Any]:
        return self._get("admin/metrics")

    def get_version(self) -> Dict[str, Any]:
        return self._get("admin/version")

    # ── Search ─────────────────────────────────────────────────────────────

    def search_basic(
        self,
        query: str = "*",
        type_name: Optional[str] = None,
        classification: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
        exclude_deleted: bool = True,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "query": query,
            "limit": limit,
            "offset": offset,
            "excludeDeletedEntities": str(exclude_deleted).lower(),
        }
        if type_name:
            params["typeName"] = type_name
        if classification:
            params["classification"] = classification
        return self._get("search/basic", params=params)

    def search_fulltext(
        self,
        query: str,
        limit: int = 25,
        offset: int = 0,
        exclude_deleted: bool = True,
    ) -> Dict[str, Any]:
        return self._get(
            "search/fulltext",
            params={
                "query": query,
                "limit": limit,
                "offset": offset,
                "excludeDeletedEntities": str(exclude_deleted).lower(),
            },
        )

    def search_dsl(
        self,
        query: str,
        limit: int = 25,
        offset: int = 0,
    ) -> Dict[str, Any]:
        return self._get(
            "search/dsl",
            params={"query": query, "limit": limit, "offset": offset},
        )

    def search_by_classification(
        self,
        classification: str,
        entity_type: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
        exclude_deleted: bool = True,
    ) -> Dict[str, Any]:
        return self.search_basic(
            query="*",
            type_name=entity_type,
            classification=classification,
            limit=limit,
            offset=offset,
            exclude_deleted=exclude_deleted,
        )

    def search_saved(self) -> Dict[str, Any]:
        return self._get("search/saved")

    # ── Entity ─────────────────────────────────────────────────────────────

    def get_entity_by_guid(
        self, guid: str, min_ext_info: bool = False, ignore_relationships: bool = False
    ) -> Dict[str, Any]:
        return self._get(
            f"entity/guid/{guid}",
            params={
                "minExtInfo": str(min_ext_info).lower(),
                "ignoreRelationships": str(ignore_relationships).lower(),
            },
        )

    def get_entity_by_attribute(
        self,
        type_name: str,
        attr_name: str,
        attr_value: str,
        min_ext_info: bool = False,
        ignore_relationships: bool = False,
    ) -> Dict[str, Any]:
        return self._get(
            f"entity/uniqueAttribute/type/{type_name}",
            params={
                f"attr:{attr_name}": attr_value,
                "minExtInfo": str(min_ext_info).lower(),
                "ignoreRelationships": str(ignore_relationships).lower(),
            },
        )

    def get_entities_by_guids(self, guids: List[str]) -> Dict[str, Any]:
        return self._get("entity/bulk", params=[("guid", g) for g in guids])

    def get_entity_classifications(self, guid: str) -> Dict[str, Any]:
        return self._get(f"entity/guid/{guid}/classifications")

    def get_entity_labels(self, guid: str) -> Dict[str, Any]:
        return self._get(f"entity/guid/{guid}/labels")

    def get_entity_audit(
        self, guid: str, count: int = 100, start_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"count": count}
        if start_key:
            params["startKey"] = start_key
        return self._get(f"entity/{guid}/audit", params=params)

    def get_entity_header(self, guid: str) -> Dict[str, Any]:
        return self._get(f"entity/guid/{guid}/header")

    def add_classification(self, guid: str, classifications: List[Dict[str, Any]]) -> None:
        self._post(f"entity/guid/{guid}/classifications", classifications)

    def remove_classification(self, guid: str, classification_name: str) -> None:
        self._delete(f"entity/guid/{guid}/classification/{classification_name}")

    def add_labels(self, guid: str, labels: List[str]) -> None:
        self._post(f"entity/guid/{guid}/labels", labels)

    def remove_labels(self, guid: str, labels: List[str]) -> None:
        self._delete(f"entity/guid/{guid}/labels")

    def update_entity_attribute(
        self, guid: str, attr_name: str, attr_value: Any
    ) -> Dict[str, Any]:
        return self._put(
            f"entity/guid/{guid}",
            params={"name": attr_name},
        )

    def create_or_update_entity(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        return self._post("entity", {"entity": entity})

    def register_typedefs(self, typedef_payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._post("types/typedefs", typedef_payload)

    def purge_entities(self, guids: List[str]) -> Any:
        return self._put("admin/purge/", guids)

    def delete_entity_permanently(
        self,
        type_name: str,
        qualified_name: str,
    ) -> Dict[str, Any]:
        entity_resp = self.get_entity_by_attribute(type_name, "qualifiedName", qualified_name)
        guid = entity_resp["entity"]["guid"]
        delete_resp = self._delete(f"entity/guid/{guid}", params={"purge": "true"})
        purge_resp: Any = None
        try:
            purge_resp = self.purge_entities([guid])
        except AtlasError:
            pass
        return {
            "status": "purged",
            "guid": guid,
            "qualifiedName": qualified_name,
            "delete_response": delete_resp,
            "purge_response": purge_resp,
        }

    # ── Lineage ────────────────────────────────────────────────────────────

    def get_lineage_by_guid(
        self,
        guid: str,
        direction: str = "BOTH",
        depth: int = 3,
    ) -> Dict[str, Any]:
        return self._get(
            f"lineage/{guid}",
            params={"direction": direction, "depth": depth},
        )

    def get_lineage_by_attribute(
        self,
        type_name: str,
        attr_name: str,
        attr_value: str,
        direction: str = "BOTH",
        depth: int = 3,
    ) -> Dict[str, Any]:
        return self._get(
            f"lineage/uniqueAttribute/type/{type_name}",
            params={
                f"attr:{attr_name}": attr_value,
                "direction": direction,
                "depth": depth,
            },
        )

    # ── Types ──────────────────────────────────────────────────────────────

    def get_all_type_defs(self) -> Dict[str, Any]:
        return self._get("types/typedefs")

    def get_entity_type_def(self, type_name: str) -> Dict[str, Any]:
        return self._get(f"types/entitydef/name/{type_name}")

    def get_classification_type_def(self, type_name: str) -> Dict[str, Any]:
        return self._get(f"types/classificationdef/name/{type_name}")

    def get_type_def_by_name(self, type_name: str) -> Dict[str, Any]:
        return self._get(f"types/typedef/name/{type_name}")

    def list_type_names(self, type_category: Optional[str] = None) -> Dict[str, Any]:
        params = {}
        if type_category:
            params["type"] = type_category
        return self._get("types/typedefs/headers", params=params or None)

    # ── Glossary ───────────────────────────────────────────────────────────

    def list_glossaries(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return self._get("glossary", params={"limit": limit, "offset": offset})

    def get_glossary(self, glossary_guid: str) -> Dict[str, Any]:
        return self._get(f"glossary/{glossary_guid}")

    def list_glossary_terms(
        self, glossary_guid: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> Any:
        if glossary_guid:
            return self._get(
                f"glossary/{glossary_guid}/terms",
                params={"limit": limit, "offset": offset},
            )
        return self._get("glossary/terms", params={"limit": limit, "offset": offset})

    def get_glossary_term(self, term_guid: str) -> Dict[str, Any]:
        return self._get(f"glossary/term/{term_guid}")

    def get_entities_for_term(self, term_guid: str, limit: int = 25, offset: int = 0) -> Any:
        return self._get(
            f"glossary/terms/{term_guid}/assignedEntities",
            params={"limit": limit, "offset": offset},
        )

    # ── Relationships ──────────────────────────────────────────────────────

    def get_relationship_by_guid(self, guid: str) -> Dict[str, Any]:
        return self._get(f"relationship/guid/{guid}")

    # ── Data contracts ─────────────────────────────────────────────────────

    def ensure_data_contract_typedef(self) -> Dict[str, Any]:
        try:
            self.get_entity_type_def(DATA_CONTRACT_TYPE)
            return {"status": "exists", "typeName": DATA_CONTRACT_TYPE}
        except AtlasError:
            return self.register_typedefs(DATA_CONTRACT_TYPEDEF)

    def get_data_contract(
        self,
        contract_id: Optional[str] = None,
        version: Optional[str] = None,
        qualified_name: Optional[str] = None,
        ignore_relationships: bool = False,
    ) -> Dict[str, Any]:
        qn = qualified_name or build_qualified_name(
            _require(contract_id, "contract_id"),
            _require(version, "version"),
        )
        return self.get_entity_by_attribute(
            DATA_CONTRACT_TYPE,
            "qualifiedName",
            qn,
            ignore_relationships=ignore_relationships,
        )

    def search_data_contracts(
        self,
        query: str = "*",
        status: Optional[str] = None,
        contract_id: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
        exclude_deleted: bool = True,
    ) -> Dict[str, Any]:
        if status or contract_id:
            clauses: List[str] = []
            if status:
                clauses.append(f'status="{status}"')
            if contract_id:
                clauses.append(f'contractId="{contract_id}"')
            dsl_query = f"{DATA_CONTRACT_TYPE} where {' and '.join(clauses)}"
            return self.search_dsl(dsl_query, limit=limit, offset=offset)
        return self.search_basic(
            query=query,
            type_name=DATA_CONTRACT_TYPE,
            limit=limit,
            offset=offset,
            exclude_deleted=exclude_deleted,
        )

    def create_data_contract(
        self,
        contract_id: str,
        version: str,
        status: str,
        quality_rules: Optional[List[str]] = None,
        qualified_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        qn = qualified_name or build_qualified_name(contract_id, version)
        attributes: Dict[str, Any] = {
            "qualifiedName": qn,
            "contractId": contract_id,
            "version": version,
            "status": status,
        }
        if quality_rules:
            attributes["quality_rules"] = quality_rules
        entity = {"typeName": DATA_CONTRACT_TYPE, "attributes": attributes}
        result = self.create_or_update_entity(entity)
        return {
            "status": "ok",
            "qualifiedName": qn,
            "contractId": contract_id,
            "version": version,
            "mutation": result,
        }

    def update_data_contract_status(
        self,
        status: str,
        contract_id: Optional[str] = None,
        version: Optional[str] = None,
        qualified_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        qn = qualified_name or build_qualified_name(
            _require(contract_id, "contract_id"),
            _require(version, "version"),
        )
        entity = {
            "typeName": DATA_CONTRACT_TYPE,
            "attributes": {
                "qualifiedName": qn,
                "status": status,
            },
        }
        result = self.create_or_update_entity(entity)
        return {"status": "ok", "qualifiedName": qn, "new_status": status, "mutation": result}

    def bind_contract_to_tables(
        self,
        table_qualified_names: List[Dict[str, str]],
        contract_id: Optional[str] = None,
        version: Optional[str] = None,
        qualified_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        qn = qualified_name or build_qualified_name(
            _require(contract_id, "contract_id"),
            _require(version, "version"),
        )
        assigned_datasets = [
            {
                "typeName": spec["type_name"],
                "uniqueAttributes": {"qualifiedName": spec["qualified_name"]},
            }
            for spec in table_qualified_names
        ]
        entity = {
            "typeName": DATA_CONTRACT_TYPE,
            "attributes": {"qualifiedName": qn},
            "relationshipAttributes": {"assigned_datasets": assigned_datasets},
        }
        result = self.create_or_update_entity(entity)
        return {
            "status": "ok",
            "qualifiedName": qn,
            "bound_tables": [spec["qualified_name"] for spec in table_qualified_names],
            "mutation": result,
        }

    def delete_data_contract(
        self,
        contract_id: Optional[str] = None,
        version: Optional[str] = None,
        qualified_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        qn = qualified_name or build_qualified_name(
            _require(contract_id, "contract_id"),
            _require(version, "version"),
        )
        return self.delete_entity_permanently(DATA_CONTRACT_TYPE, qn)


def _require(value: Optional[str], name: str) -> str:
    if not value:
        raise ValueError(f"{name} is required when qualified_name is not provided")
    return value
