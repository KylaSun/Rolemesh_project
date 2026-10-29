"""Optional GTE scorer. No model is downloaded or loaded during package import."""
import math
from functools import lru_cache

MODEL_ID = "Alibaba-NLP/gte-multilingual-base"


class GTEScorer:
    def __init__(self, model_path, *, revision=None, local_files_only=True):
        from sentence_transformers import SentenceTransformer
        # Official model requires custom code. Prefer a reviewed, pinned local snapshot.
        self.model = SentenceTransformer(
            model_path, revision=revision, trust_remote_code=True,
            local_files_only=local_files_only,
        )
        self.model_id = MODEL_ID
        self.revision = revision or "local-snapshot-unversioned"

    @lru_cache(maxsize=2048)
    def _encode(self, text):
        return self.model.encode(text, normalize_embeddings=True, convert_to_numpy=True)

    def similarity(self, left, right):
        # Normalized vector dot product is cosine similarity.
        value = float(self._encode(left) @ self._encode(right))
        if not math.isfinite(value):
            raise ValueError("Model returned non-finite similarity")
        return max(-1.0, min(1.0, value))


def to_score(similarity, low=0.4, high=0.8):
    """Provisional calibration only; not a learned probability."""
    if not math.isfinite(similarity) or high <= low:
        raise ValueError("Invalid semantic score configuration")
    return 100.0 * max(0.0, min(1.0, (similarity - low) / (high - low)))
