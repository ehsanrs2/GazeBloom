"""Use R4's frozen signed-template metric without changing its definition."""
from __future__ import annotations

import numpy as np

from experiments.r4_directional_controls.evaluate import signed_alignment


def artifact_proxy(rgb: np.ndarray) -> float:
    """Mean unsigned chromatic deviation in assumed linear RGB, not comfort."""
    if rgb.ndim != 3 or rgb.shape[0] != 3 or not np.isfinite(rgb).all():
        raise ValueError("expected finite 3-channel image")
    return float(np.mean(np.abs(rgb - rgb.mean(axis=0, keepdims=True))))
