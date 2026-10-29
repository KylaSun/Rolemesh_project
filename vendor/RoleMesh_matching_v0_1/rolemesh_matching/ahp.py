"""Initial subjective AHP judgments; weights are computed, not fitted to data."""
import math

CRITERIA = ("skills", "role", "domain", "time")
MATRIX = (
    (1, 2, 3, 4),
    (1 / 2, 1, 2, 3),
    (1 / 3, 1 / 2, 1, 2),
    (1 / 4, 1 / 3, 1 / 2, 1),
)


def calculate_weights(matrix=MATRIX):
    n = len(matrix)
    if n != 4 or any(len(row) != n for row in matrix):
        raise ValueError("This implementation supports four criteria only")
    for i in range(n):
        for j in range(n):
            x = matrix[i][j]
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0:
                raise ValueError("AHP entries must be positive finite numbers")
            if abs(x * matrix[j][i] - 1) > 1e-8:
                raise ValueError("AHP matrix must be reciprocal")
    weights = [1 / n] * n
    for _ in range(1000):
        product = [sum(row[j] * weights[j] for j in range(n)) for row in matrix]
        total = sum(product)
        updated = [x / total for x in product]
        error = max(abs(a - b) for a, b in zip(weights, updated))
        weights = updated
        if error < 1e-12:
            break
    aw = [sum(row[j] * weights[j] for j in range(n)) for row in matrix]
    eigenvalue = sum(x / w for x, w in zip(aw, weights)) / n
    ci = max(0.0, (eigenvalue - n) / (n - 1))
    cr = ci / 0.90
    if cr >= 0.10:
        raise ValueError("AHP consistency ratio must be below 0.10")
    return {"weights": dict(zip(CRITERIA, weights)), "lambda_max": eigenvalue, "CI": ci, "CR": cr}
