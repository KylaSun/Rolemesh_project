"""Run: pip install -r requirements.txt; python demo.py. No model download."""
import json
from pathlib import Path
from rolemesh_matching import recommend, calculate_weights
from rolemesh_matching.integration import run_request

root = Path(__file__).resolve().parent
data = json.loads((root / "examples/input.json").read_text(encoding="utf-8"))
output = run_request(data)
(root / "examples/output.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
(root / "examples/ahp.json").write_text(json.dumps(calculate_weights(), ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"projects": output["projects"], "roles": len(output["comparisons"]), "AHP": calculate_weights()}, ensure_ascii=False, indent=2))
