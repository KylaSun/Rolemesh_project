"""Explicit optional model download, invoked by the operator only."""
import argparse
from huggingface_hub import HfApi, snapshot_download
from rolemesh_matching.semantic import MODEL_ID

parser = argparse.ArgumentParser()
parser.add_argument("--destination", default="models/gte")
args = parser.parse_args()
revision = HfApi().model_info(MODEL_ID).sha
path = snapshot_download(repo_id=MODEL_ID, revision=revision, local_dir=args.destination)
print("Model snapshot:", path)
print("Revision:", revision)
print("Use this revision with demo_gte.py --revision")
