from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

JsonArrayInput = Union[str, Sequence[Any], None]

DATA_CONTRACT_TYPE = "data_contract"
DATA_CONTRACT_RELATIONSHIP = "datacontract_dataset_assignment"
DATA_CONTRACT_TYPE_VERSION = "2.2"
SUPPORTED_TABLE_TYPES = frozenset({"hive_table", "iceberg_table"})

STRUCT_SCHEMA_PROPERTY = "odcs_schema_property"
STRUCT_SCHEMA_OBJECT = "odcs_schema_object"
STRUCT_QUALITY_RULE = "odcs_quality_rule"
STRUCT_SLA_PROPERTY = "odcs_sla_property"

_ODCS_KEY_ALIASES: Dict[str, str] = {
    "businessName": "business_name",
    "logicalType": "logical_type",
    "physicalType": "physical_type",
    "physicalName": "physical_name",
    "primaryKey": "primary_key",
    "isRequired": "is_required",
    "required": "is_required",
    "ruleType": "rule_type",
    "type": "rule_type",
    "mustBeLessThan": "threshold",
    "must_be_less_than": "threshold",
    "valueExt": "value_ext",
    "columnName": "name",
    "column_name": "name",
    "dataType": "physical_type",
    "data_type": "physical_type",
    "slaDefaultElement": "sla_default_element",
}

_DATA_CONTRACT_PRESERVED_ATTRS = (
    "contractId",
    "version",
    "status",
    "quality_rules",
    "name",
    "domain",
    "data_product",
    "tenant",
    "description_purpose",
    "description_limitations",
    "tags",
    "consumer",
    "sla_default_element",
    "freshness_sla",
    "freshness_quality_threshold",
    "schema_summary",
    "odcs_document",
    "schema_objects",
    "schema_properties",
    "quality",
    "sla_properties",
)

def _optional_attr(name: str, type_name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "typeName": type_name,
        "isOptional": True,
        "cardinality": "SINGLE",
    }


def _required_attr(name: str, type_name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "typeName": type_name,
        "isOptional": False,
        "cardinality": "SINGLE",
    }


DATA_CONTRACT_STRUCT_DEFS = [
    {
        "name": STRUCT_SCHEMA_PROPERTY,
        "description": "ODCS schema property (column/field)",
        "typeVersion": "1.1",
        "attributeDefs": [
            _required_attr("name", "string"),
            _optional_attr("object_name", "string"),
            _optional_attr("business_name", "string"),
            _optional_attr("logical_type", "string"),
            _optional_attr("physical_type", "string"),
            _optional_attr("is_required", "boolean"),
            _optional_attr("primary_key", "boolean"),
            _optional_attr("description", "string"),
        ],
    },
    {
        "name": STRUCT_SCHEMA_OBJECT,
        "description": "ODCS schema object (table/document)",
        "typeVersion": "1.1",
        "attributeDefs": [
            _required_attr("name", "string"),
            _optional_attr("logical_type", "string"),
            _optional_attr("physical_type", "string"),
            _optional_attr("physical_name", "string"),
            _optional_attr("description", "string"),
        ],
    },
    {
        "name": STRUCT_QUALITY_RULE,
        "description": "ODCS data quality rule",
        "typeVersion": "1.0",
        "attributeDefs": [
            _optional_attr("rule_type", "string"),
            _optional_attr("metric", "string"),
            _optional_attr("name", "string"),
            _optional_attr("description", "string"),
            _optional_attr("threshold", "string"),
            _optional_attr("unit", "string"),
            _optional_attr("element", "string"),
            _optional_attr("query", "string"),
            _optional_attr("engine", "string"),
        ],
    },
    {
        "name": STRUCT_SLA_PROPERTY,
        "description": "ODCS SLA property",
        "typeVersion": "1.0",
        "attributeDefs": [
            _required_attr("property", "string"),
            _optional_attr("value", "string"),
            _optional_attr("value_ext", "string"),
            _optional_attr("unit", "string"),
            _optional_attr("element", "string"),
            _optional_attr("driver", "string"),
        ],
    },
]

_DATA_CONTRACT_V2_ATTRS: List[Dict[str, Any]] = [
    _required_attr("contractId", "string") | {"isUnique": True, "isIndexable": True},
    _required_attr("status", "string"),
    _required_attr("version", "string"),
    {
        "name": "quality_rules",
        "typeName": "array<string>",
        "isOptional": True,
        "cardinality": "SET",
    },
    _optional_attr("name", "string") | {"isIndexable": True},
    _optional_attr("domain", "string") | {"isIndexable": True},
    _optional_attr("data_product", "string") | {"isIndexable": True},
    _optional_attr("tenant", "string"),
    _optional_attr("description_purpose", "string"),
    _optional_attr("description_limitations", "string"),
    {
        "name": "tags",
        "typeName": "array<string>",
        "isOptional": True,
        "cardinality": "SET",
    },
    {
        "name": "consumer",
        "typeName": "array<string>",
        "isOptional": True,
        "cardinality": "SET",
        "isIndexable": True,
    },
    _optional_attr("sla_default_element", "string"),
    _optional_attr("freshness_sla", "string") | {"isIndexable": True},
    _optional_attr("freshness_quality_threshold", "string") | {"isIndexable": True},
    _optional_attr("schema_summary", "string"),
    _optional_attr("odcs_document", "string"),
    {
        "name": "schema_objects",
        "typeName": f"array<{STRUCT_SCHEMA_OBJECT}>",
        "isOptional": True,
        "cardinality": "SET",
    },
    {
        "name": "schema_properties",
        "typeName": f"array<{STRUCT_SCHEMA_PROPERTY}>",
        "isOptional": True,
        "cardinality": "SET",
    },
    {
        "name": "quality",
        "typeName": f"array<{STRUCT_QUALITY_RULE}>",
        "isOptional": True,
        "cardinality": "SET",
    },
    {
        "name": "sla_properties",
        "typeName": f"array<{STRUCT_SLA_PROPERTY}>",
        "isOptional": True,
        "cardinality": "SET",
    },
]

DATA_CONTRACT_TYPEDEF: Dict[str, Any] = {
    "structDefs": DATA_CONTRACT_STRUCT_DEFS,
    "entityDefs": [
        {
            "name": DATA_CONTRACT_TYPE,
            "superTypes": ["Referenceable"],
            "serviceType": "data_mesh",
            "typeVersion": DATA_CONTRACT_TYPE_VERSION,
            "description": "Repraesentiert einen ODCS Data Contract (Hybrid v2)",
            "attributeDefs": _DATA_CONTRACT_V2_ATTRS,
        }
    ],
    "relationshipDefs": [
        {
            "name": DATA_CONTRACT_RELATIONSHIP,
            "relationshipCategory": "AGGREGATION",
            "propagateTags": "ONE_TO_TWO",
            "endDef1": {
                "type": DATA_CONTRACT_TYPE,
                "name": "assigned_datasets",
                "cardinality": "SET",
                "isContainer": True,
            },
            "endDef2": {
                "type": "DataSet",
                "name": "governing_contracts",
                "cardinality": "SET",
                "isContainer": False,
            },
        }
    ],
}

DATA_CONTRACT_TYPEDEF_UPGRADE: Dict[str, Any] = {
    "entityDefs": [
        {
            "name": DATA_CONTRACT_TYPE,
            "typeVersion": DATA_CONTRACT_TYPE_VERSION,
            "attributeDefs": _DATA_CONTRACT_V2_ATTRS,
        }
    ],
}


def build_struct_typedef_upgrade(
    existing_def: Mapping[str, Any],
    target_def: Mapping[str, Any],
) -> Dict[str, Any]:
    existing_attr_defs = list(existing_def.get("attributeDefs") or [])
    existing_names = {attr["name"] for attr in existing_attr_defs}
    for attr in target_def.get("attributeDefs") or []:
        if attr["name"] not in existing_names:
            existing_attr_defs.append(attr)

    return {
        "name": target_def["name"],
        "typeVersion": target_def.get("typeVersion", existing_def.get("typeVersion", "1.0")),
        "attributeDefs": existing_attr_defs,
    }


def build_entity_typedef_upgrade(existing_def: Mapping[str, Any]) -> Dict[str, Any]:
    existing_attr_defs = list(existing_def.get("attributeDefs") or [])
    existing_names = {attr["name"] for attr in existing_attr_defs}
    for attr in _DATA_CONTRACT_V2_ATTRS:
        if attr["name"] not in existing_names:
            existing_attr_defs.append(attr)

    entity_def: Dict[str, Any] = {
        "name": DATA_CONTRACT_TYPE,
        "superTypes": list(existing_def.get("superTypes") or ["Referenceable"]),
        "serviceType": existing_def.get("serviceType", "data_mesh"),
        "typeVersion": DATA_CONTRACT_TYPE_VERSION,
        "attributeDefs": existing_attr_defs,
    }
    description = existing_def.get("description")
    if description:
        entity_def["description"] = description
    return entity_def


def build_qualified_name(contract_id: str, version: str) -> str:
    return f"{contract_id}@{version}"


def typedef_needs_upgrade(existing_def: Mapping[str, Any]) -> bool:
    current = str(existing_def.get("typeVersion") or "1.0")
    if _version_key(current) < _version_key(DATA_CONTRACT_TYPE_VERSION):
        return True
    existing_names = {attr["name"] for attr in existing_def.get("attributeDefs") or []}
    required_names = {attr["name"] for attr in _DATA_CONTRACT_V2_ATTRS}
    return not required_names.issubset(existing_names)


def _version_key(version: str) -> tuple[int, ...]:
    parts: List[int] = []
    for piece in version.split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def coerce_json_array(value: JsonArrayInput, field_name: str) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        parsed = json.loads(stripped)
        if not isinstance(parsed, list):
            raise ValueError(f"{field_name} JSON must be an array")
        return parsed
    raise ValueError(f"{field_name} must be a JSON array string or a list")


def parse_quality_rules(quality_rules: JsonArrayInput | str) -> List[str]:
    if not quality_rules:
        return []
    if isinstance(quality_rules, list):
        rules: List[str] = []
        for item in quality_rules:
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, Mapping):
                text = str(
                    item.get("description")
                    or item.get("name")
                    or item.get("rule")
                    or item.get("metric")
                    or json.dumps(item, ensure_ascii=False)
                ).strip()
            else:
                text = str(item).strip()
            if text:
                rules.append(text)
        return rules
    if not isinstance(quality_rules, str):
        raise ValueError("quality_rules must be a string, list, or JSON array string")
    stripped = quality_rules.strip()
    if stripped.startswith("["):
        parsed = json.loads(stripped)
        if not isinstance(parsed, list):
            raise ValueError("quality_rules JSON must be an array of strings")
        return parse_quality_rules(parsed)
    return [rule.strip() for rule in stripped.split(",") if rule.strip()]


def parse_json_array(value: JsonArrayInput, field_name: str) -> List[Any]:
    return coerce_json_array(value, field_name)


def parse_tags(tags: JsonArrayInput | str) -> List[str]:
    return _parse_string_array(tags, "tags")


def parse_consumers(consumers: JsonArrayInput | str) -> List[str]:
    """Parse contract consumers (roles, groups, or persons)."""
    return _parse_string_array(consumers, "consumer")


def _parse_string_array(value: JsonArrayInput | str, field_name: str) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string, list, or JSON array string")
    stripped = value.strip()
    if stripped.startswith("["):
        parsed = json.loads(stripped)
        if not isinstance(parsed, list):
            raise ValueError(f"{field_name} JSON must be an array of strings")
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [part.strip() for part in stripped.split(",") if part.strip()]


def _normalize_mapping(raw: Mapping[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in raw.items():
        atlas_key = _ODCS_KEY_ALIASES.get(key, key)
        if key in {"nullable", "Nullable"}:
            if isinstance(value, bool):
                normalized["is_required"] = not value
            elif isinstance(value, str):
                normalized["is_required"] = value.strip().upper() in {"NO", "FALSE", "0", "N"}
            continue
        if atlas_key == "nullable":
            continue
        if atlas_key == "properties" and isinstance(value, list):
            normalized[atlas_key] = [_normalize_schema_property(item) for item in value]
        elif isinstance(value, Mapping):
            normalized[atlas_key] = _normalize_mapping(value)
        elif isinstance(value, bool):
            normalized[atlas_key] = value
        elif value is None:
            continue
        else:
            normalized[atlas_key] = str(value) if atlas_key == "threshold" and not isinstance(value, str) else value
    return normalized


def _normalize_schema_property(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("schema property entries must be JSON objects")
    return _normalize_mapping(raw)


def parse_schema_objects(schema_objects: JsonArrayInput) -> List[Dict[str, Any]]:
    items = coerce_json_array(schema_objects, "schema_objects")
    result: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("schema_objects entries must be JSON objects")
        normalized = _normalize_mapping(item)
        if "name" not in normalized:
            raise ValueError("each schema object requires a name")
        result.append(normalized)
    return result


def parse_struct_quality_rules(quality: JsonArrayInput) -> List[Dict[str, Any]]:
    items = coerce_json_array(quality, "quality")
    result: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("quality entries must be JSON objects")
        normalized = _normalize_mapping(item)
        if "threshold" in normalized and normalized["threshold"] is not None:
            normalized["threshold"] = str(normalized["threshold"])
        result.append(normalized)
    return result


def parse_struct_sla_properties(sla_properties: JsonArrayInput) -> List[Dict[str, Any]]:
    items = coerce_json_array(sla_properties, "sla_properties")
    result: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("sla_properties entries must be JSON objects")
        normalized = _normalize_mapping(item)
        if "property" not in normalized:
            raise ValueError("each sla property requires a property name")
        if "value" in normalized and normalized["value"] is not None:
            normalized["value"] = str(normalized["value"])
        if "value_ext" in normalized and normalized["value_ext"] is not None:
            normalized["value_ext"] = str(normalized["value_ext"])
        result.append(normalized)
    return result


def flatten_schema_for_atlas(
    schema_objects: List[Mapping[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Atlas cannot persist nested struct arrays; store columns in schema_properties."""
    atlas_objects: List[Dict[str, Any]] = []
    atlas_properties: List[Dict[str, Any]] = []
    for obj in schema_objects:
        object_name = str(obj.get("name", "")).strip()
        if not object_name:
            raise ValueError("each schema object requires a name")
        atlas_objects.append(
            {
                key: value
                for key, value in _normalize_mapping(obj).items()
                if key != "properties"
            }
        )
        for prop in obj.get("properties") or []:
            if not isinstance(prop, Mapping):
                raise ValueError("schema property entries must be JSON objects")
            flat = _normalize_mapping(prop)
            flat["object_name"] = object_name
            atlas_properties.append(flat)
    return atlas_objects, atlas_properties


def build_schema_summary(
    schema_objects: List[Mapping[str, Any]],
    schema_properties: Optional[List[Mapping[str, Any]]] = None,
) -> str:
    if not schema_objects and not schema_properties:
        return ""
    if schema_properties is not None:
        property_count = len(schema_properties)
    else:
        property_count = sum(len(obj.get("properties") or []) for obj in schema_objects)
    return f"{len(schema_objects)} objects, {property_count} properties"


def derive_freshness_sla(sla_properties: List[Mapping[str, Any]]) -> Optional[str]:
    for prop in sla_properties:
        if str(prop.get("property", "")).lower() == "freshness":
            value = str(prop.get("value", "")).strip()
            unit = str(prop.get("unit", "")).strip()
            if not value:
                return None
            return f"{value}{unit}" if unit else value
    return None


def derive_freshness_quality_threshold(quality: List[Mapping[str, Any]]) -> Optional[str]:
    for rule in quality:
        metric = rule.get("metric") or rule.get("rule")
        if metric and str(metric).lower() == "freshness":
            threshold = rule.get("threshold")
            unit = str(rule.get("unit", "")).strip()
            if threshold is None:
                return None
            threshold_text = str(threshold).strip()
            return f"{threshold_text}{unit}" if unit else threshold_text
    return None


_STRUCT_ARRAY_ATTRS = frozenset(
    {"schema_objects", "schema_properties", "quality", "sla_properties"}
)


def atlas_struct_array_to_writer(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    writer_values: List[Any] = []
    for item in value:
        if isinstance(item, Mapping) and "attributes" in item:
            normalized = {
                k: v for k, v in item["attributes"].items() if v is not None and v != []
            }
        elif isinstance(item, Mapping):
            normalized = {k: v for k, v in item.items() if v is not None and v != []}
        else:
            writer_values.append(item)
            continue
        normalized.pop("properties", None)
        writer_values.append(normalized)
    return writer_values


def preserve_contract_attributes(existing_attrs: Mapping[str, Any]) -> Dict[str, Any]:
    preserved: Dict[str, Any] = {}
    for key in _DATA_CONTRACT_PRESERVED_ATTRS:
        if key in existing_attrs and existing_attrs[key] is not None:
            value = existing_attrs[key]
            if key in _STRUCT_ARRAY_ATTRS:
                value = atlas_struct_array_to_writer(value)
            preserved[key] = value
    preserved["qualifiedName"] = existing_attrs["qualifiedName"]
    return preserved


def build_data_contract_attributes(
    *,
    qualified_name: str,
    contract_id: str,
    version: str,
    status: str,
    quality_rules: Optional[List[str]] = None,
    name: Optional[str] = None,
    domain: Optional[str] = None,
    data_product: Optional[str] = None,
    tenant: Optional[str] = None,
    description_purpose: Optional[str] = None,
    description_limitations: Optional[str] = None,
    tags: Optional[List[str]] = None,
    consumer: Optional[List[str]] = None,
    sla_default_element: Optional[str] = None,
    odcs_document: Optional[str] = None,
    schema_objects: Optional[List[Dict[str, Any]]] = None,
    quality: Optional[List[Dict[str, Any]]] = None,
    sla_properties: Optional[List[Dict[str, Any]]] = None,
    existing_attrs: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if existing_attrs:
        attributes = preserve_contract_attributes(existing_attrs)
    else:
        attributes = {
            "qualifiedName": qualified_name,
            "contractId": contract_id,
            "version": version,
            "status": status,
        }

    attributes["qualifiedName"] = qualified_name
    attributes["contractId"] = contract_id
    attributes["version"] = version
    attributes["status"] = status

    optional_strings = {
        "name": name,
        "domain": domain,
        "data_product": data_product,
        "tenant": tenant,
        "description_purpose": description_purpose,
        "description_limitations": description_limitations,
        "sla_default_element": sla_default_element,
        "odcs_document": odcs_document,
    }
    for key, value in optional_strings.items():
        if value is not None:
            attributes[key] = value

    if quality_rules is not None:
        attributes["quality_rules"] = quality_rules
    if tags is not None:
        attributes["tags"] = tags
    if consumer is not None:
        attributes["consumer"] = consumer
    if schema_objects is not None:
        atlas_objects, atlas_properties = flatten_schema_for_atlas(schema_objects)
        attributes["schema_objects"] = atlas_objects
        attributes["schema_properties"] = atlas_properties
        attributes["schema_summary"] = build_schema_summary(atlas_objects, atlas_properties)
    if quality is not None:
        attributes["quality"] = quality
        freshness_quality = derive_freshness_quality_threshold(quality)
        if freshness_quality:
            attributes["freshness_quality_threshold"] = freshness_quality
    if sla_properties is not None:
        attributes["sla_properties"] = sla_properties
        freshness_sla = derive_freshness_sla(sla_properties)
        if freshness_sla:
            attributes["freshness_sla"] = freshness_sla

    return attributes


def parse_table_bindings(
    table_qualified_names: str,
    table_type: str = "hive_table",
) -> List[Dict[str, str]]:
    if table_type not in SUPPORTED_TABLE_TYPES:
        supported = ", ".join(sorted(SUPPORTED_TABLE_TYPES))
        raise ValueError(f"Unsupported table_type '{table_type}'. Use one of: {supported}")

    bindings: List[Dict[str, str]] = []
    for qualified_name in table_qualified_names.split(","):
        name = qualified_name.strip()
        if name:
            bindings.append({"type_name": table_type, "qualified_name": name})
    if not bindings:
        raise ValueError("At least one table qualifiedName is required")
    return bindings
