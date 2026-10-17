"""A3: prüft Antworten aus openapi_samples.py gegen die Schemas in challenge/contract/openapi.yaml.

    python openapi_check.py <samples.json> [openapi.yaml]     (Referenz-venv: jsonschema, pyyaml)
Exit 1 bei Verstoß. Formate (`date-time`) werden mitgeprüft.
"""

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

spec_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("challenge/contract/openapi.yaml")
spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
samples = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
bad = checked = 0
for name, instances in samples.items():
    root = {"$ref": f"#/components/schemas/{name}", "components": spec["components"]}
    validator = Draft202012Validator(root, format_checker=FormatChecker())
    for index, instance in enumerate(instances):
        checked += 1
        errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
        if errors:
            bad += 1
            print(f"ABWEICHUNG {name}[{index}]:")
            for error in errors[:4]:
                print("   ", "/".join(str(p) for p in error.path) or "$", "->", error.message[:140])
print(f"geprüft: {checked} Antworten in {len(samples)} Schemas, Abweichungen: {bad}")
sys.exit(1 if bad else 0)
