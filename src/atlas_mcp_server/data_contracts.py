from __future__ import annotations

from typing import Any, Dict, List

DATA_CONTRACT_TYPE = "data_contract"
DATA_CONTRACT_RELATIONSHIP = "datacontract_dataset_assignment"
SUPPORTED_TABLE_TYPES = frozenset({"hive_table", "iceberg_table"})

DATA_CONTRACT_TYPEDEF: Dict[str, Any] = {
    "entityDefs": [
        {
            "name": DATA_CONTRACT_TYPE,
            "superTypes": ["Referenceable"],
            "serviceType": "data_mesh",
            "typeVersion": "1.0",
            "description": "Repraesentiert einen ODCS Data Contract",
            "attributeDefs": [
                {
                    "name": "contractId",
                    "typeName": "string",
                    "isOptional": False,
                    "cardinality": "SINGLE",
                    "isUnique": True,
                    "isIndexable": True,
                },
                {
                    "name": "status",
                    "typeName": "string",
                    "isOptional": False,
                    "cardinality": "SINGLE",
                },
                {
                    "name": "version",
                    "typeName": "string",
                    "isOptional": False,
                    "cardinality": "SINGLE",
                },
                {
                    "name": "quality_rules",
                    "typeName": "array<string>",
                    "isOptional": True,
                    "cardinality": "SET",
                },
            ],
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


def build_qualified_name(contract_id: str, version: str) -> str:
    return f"{contract_id}@{version}"


def parse_quality_rules(quality_rules: str | None) -> List[str]:
    if not quality_rules:
        return []
    stripped = quality_rules.strip()
    if stripped.startswith("["):
        import json

        parsed = json.loads(stripped)
        if not isinstance(parsed, list):
            raise ValueError("quality_rules JSON must be an array of strings")
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [rule.strip() for rule in stripped.split(",") if rule.strip()]


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
