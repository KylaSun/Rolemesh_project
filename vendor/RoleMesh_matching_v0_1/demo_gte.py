"""Run after installing optional dependencies and downloading a model snapshot.

python demo_gte.py --model-path ./models/gte --revision SNAPSHOT_COMMIT
This script does not download anything; it fails explicitly if the model is absent.
"""
import argparse
import json
from pathlib import Path
from rolemesh_matching import recommend
from rolemesh_matching.integration import run_request
from rolemesh_matching.semantic import GTEScorer

parser = argparse.ArgumentParser()
parser.add_argument("--model-path", required=True)
parser.add_argument("--revision", required=True, help="Record downloaded snapshot commit")
args = parser.parse_args()
root = Path(__file__).resolve().parent
data = json.loads((root / "examples/input_semantic.json").read_text(encoding="utf-8"))
scorer = GTEScorer(args.model_path, revision=args.revision, local_files_only=True)
result = run_request(data, semantic=scorer)
(root / "examples/output_semantic.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print("Wrote examples/output_semantic.json using the actual local GTE model")
