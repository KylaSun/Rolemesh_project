"""Conservative label mapping using the repository's exact seed vocabulary."""
import json
from importlib.resources import files


def normalize_labels(labels, category):
    """Preserve all original labels; partial/unknown mapping stays unknown.

    Does not split prose, infer levels, expand skill claims or parse time ranges.
    Callers explicitly transfer codes/status/raw to the corresponding DTO field.
    """
    if category not in ('skills', 'roles', 'domains', 'languages'):
        raise ValueError('Unsupported vocabulary category')
    if not isinstance(labels, list) or any(not isinstance(v, str) or not v.strip() for v in labels):
        raise ValueError('labels must be an array of nonempty strings')
    book = json.loads(files('rolemesh_matching').joinpath('data', 'codebook_seed.json').read_text(encoding='utf-8'))
    lookup = {}
    for item in book[category]:
        for alias in (item['code'], item['label'], *item.get('aliases', [])):
            key = alias.strip().casefold()
            if key in lookup and lookup[key] != item['code']:
                raise ValueError('Ambiguous vocabulary alias')
            lookup[key] = item['code']
    codes, unknown = [], []
    for label in labels:
        code = lookup.get(label.strip().casefold())
        if code is None:
            unknown.append(label)
        elif code not in codes:
            codes.append(code)
    return {'codes':codes, 'raw':list(labels), 'unknown_labels':unknown,
            'status':'unknown' if unknown else 'provided'}
