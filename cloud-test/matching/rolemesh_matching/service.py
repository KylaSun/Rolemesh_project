"""Optional backend boundary; no routes, authorization or database assumptions."""
from .integration import run_request, run_profiles_request, _validate_schema


class SemanticUnavailable(RuntimeError):
    """Only model-origin failures trigger the explicit fallback path."""


class _GuardedModel:
    def __init__(self, model):
        self.model = model
        self.model_id = getattr(model, 'model_id', None)
        self.revision = getattr(model, 'revision', None)

    def similarity(self, left, right):
        try:
            value = self.model.similarity(left, right)
            # Validate here so invalid model output is also a model-origin failure.
            from .semantic import to_score
            to_score(value)
            return value
        except Exception as error:
            raise SemanticUnavailable('Optional semantic model unavailable') from error


def run_matching_service(request, *, direction='projects', semantic=None):
    """Optional model errors retry with rules only; data/errors never become [].

    Existing run_request still propagates model errors. This explicit adapter is
    opt-in. Missing semantic criteria remain missing on fallback, not fake scores.
    """
    if direction not in ('projects', 'profiles'):
        raise ValueError('direction must be projects or profiles')
    runner = run_request if direction == 'projects' else run_profiles_request
    try:
        return runner(request, semantic=_GuardedModel(semantic) if semantic is not None else None)
    except SemanticUnavailable:
        result = runner(request)
        for group in ('comparisons', 'recommendations'):
            for row in result[group]:
                row['warnings'] = sorted(set(row['warnings'] + ['semantic_unavailable_fallback']))
        _validate_schema(result, 'output' if direction == 'projects' else 'profiles-output')
        return result
