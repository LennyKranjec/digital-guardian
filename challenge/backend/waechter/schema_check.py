"""Kleiner JSON-Schema-Prüfer (Teilmenge von Draft 2020-12), da `jsonschema` nicht installiert ist.

Unterstützt genau die im Vertrag `contract/content.schema.json` verwendeten Schlüsselwörter:
`type`, `enum`, `const`, `pattern`, `minLength`, `minimum`, `maximum`, `minItems`, `maxItems`,
`required`, `properties`, `additionalProperties`, `items`, `propertyNames`, `$ref` (lokal), `format`
(nur `date-time`). Unbekannte Schlüsselwörter werden bewusst ignoriert, **außer** sie sind nicht in
`IGNORED` geführt: dann scheitert die Prüfung laut (`UnsupportedSchema`), damit der Vertrag nie
stillschweigend ungeprüft bleibt.

Fehlermeldungen nennen Feldpfad und Regel, **nie Werte** (kein Leck von Inhalten in Logs).
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

IGNORED = frozenset(
    {"$schema", "$id", "$defs", "title", "description", "default", "examples", "$comment"}
)
SUPPORTED = frozenset(
    {
        "type",
        "enum",
        "const",
        "pattern",
        "minLength",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "required",
        "properties",
        "additionalProperties",
        "items",
        "propertyNames",
        "$ref",
        "format",
    }
)


class UnsupportedSchema(ValueError):
    """Das Schema nutzt ein Schlüsselwort, das dieser Prüfer nicht kennt."""


@dataclass(frozen=True)
class Issue:
    path: str
    message: str


def _type_ok(value: Any, name: str) -> bool:
    if name == "string":
        return isinstance(value, str)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "null":
        return value is None
    raise UnsupportedSchema(f"unknown type {name!r}")


def _resolve(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise UnsupportedSchema("only local $ref is supported")
    node: Any = root
    for part in ref[2:].split("/"):
        node = node[part]
    if not isinstance(node, dict):
        raise UnsupportedSchema("$ref must point to an object")
    return node


def _is_datetime(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _child(path: str, key: str | int) -> str:
    return f"{path}[{key}]" if isinstance(key, int) else f"{path}.{key}"


def validate(instance: Any, schema: dict[str, Any], root: dict[str, Any]) -> list[Issue]:
    """Liefert alle Verstöße von `instance` gegen `schema` (leer = gültig)."""
    issues: list[Issue] = []
    _walk(instance, schema, root, "$", issues)
    return issues


def _walk(
    value: Any, schema: dict[str, Any], root: dict[str, Any], path: str, out: list[Issue]
) -> None:
    unknown = set(schema) - SUPPORTED - IGNORED
    if unknown:
        raise UnsupportedSchema(f"unsupported keyword at {path}: {sorted(unknown)}")
    if "$ref" in schema:
        _walk(value, _resolve(root, schema["$ref"]), root, path, out)
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(value, n) for n in names):
            out.append(Issue(path, f"wrong type, expected {' or '.join(names)}"))
            return
    if "const" in schema and (value != schema["const"] or type(value) is not type(schema["const"])):
        out.append(Issue(path, "does not match the required constant"))
    if "enum" in schema and value not in schema["enum"]:
        out.append(Issue(path, "not one of the allowed values"))
    if isinstance(value, str):
        _check_string(value, schema, path, out)
    if isinstance(value, int | float) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            out.append(Issue(path, "below the minimum"))
        if "maximum" in schema and value > schema["maximum"]:
            out.append(Issue(path, "above the maximum"))
    if isinstance(value, list):
        _check_array(value, schema, root, path, out)
    if isinstance(value, dict):
        _check_object(value, schema, root, path, out)


def _check_string(value: str, schema: dict[str, Any], path: str, out: list[Issue]) -> None:
    if "minLength" in schema and len(value) < schema["minLength"]:
        out.append(Issue(path, "too short"))
    if "pattern" in schema and re.search(schema["pattern"], value) is None:
        out.append(Issue(path, "does not match the required pattern"))
    if schema.get("format") == "date-time" and not _is_datetime(value):
        out.append(Issue(path, "not an ISO 8601 date-time with time zone"))


def _check_array(
    value: list[Any], schema: dict[str, Any], root: dict[str, Any], path: str, out: list[Issue]
) -> None:
    if "minItems" in schema and len(value) < schema["minItems"]:
        out.append(Issue(path, "too few items"))
    if "maxItems" in schema and len(value) > schema["maxItems"]:
        out.append(Issue(path, "too many items"))
    if "items" in schema:
        for index, element in enumerate(value):
            _walk(element, schema["items"], root, _child(path, index), out)


def _check_object(
    value: dict[str, Any], schema: dict[str, Any], root: dict[str, Any], path: str, out: list[Issue]
) -> None:
    for key in schema.get("required", []):
        if key not in value:
            out.append(Issue(_child(path, key), "required field is missing"))
    properties: dict[str, Any] = schema.get("properties", {})
    extra = schema.get("additionalProperties", True)
    for key, element in value.items():
        key_path = _child(path, str(key))
        if "propertyNames" in schema:
            _walk(key, schema["propertyNames"], root, f"{key_path}<key>", out)
        if key in properties:
            _walk(element, properties[key], root, key_path, out)
        elif extra is False:
            out.append(Issue(key_path, "additional field is not allowed"))
        elif isinstance(extra, dict):
            _walk(element, extra, root, key_path, out)
