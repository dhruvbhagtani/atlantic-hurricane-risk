"""Validated exposure and vulnerability inputs, with explicit wind conventions."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .model import DAMAGE_NODES, WIND_NODES


def default_vulnerability():
    return {"wind_nodes_ms": WIND_NODES.copy(),
            "damage_nodes": {k: v.copy() for k, v in DAMAGE_NODES.items()},
            "metadata": {"averaging_minutes": 1, "height_m": 10,
                         "wind_type": "sustained", "units": "m/s",
                         "exposure": "local", "source": "Explicit educational assumptions"}}


def load_vulnerability(path=None):
    if path is None:
        return default_vulnerability()
    curves = json.loads(Path(path).read_text())
    metadata = curves.get("metadata", {})
    for key, value in {"averaging_minutes": 1, "height_m": 10, "wind_type": "sustained",
                       "units": "m/s", "exposure": "local"}.items():
        if metadata.get(key) != value:
            raise ValueError(f"Vulnerability {key} must be {value!r}; convert incompatible curves explicitly")
    if not isinstance(metadata.get("source"), str) or not metadata["source"].strip():
        raise ValueError("Vulnerability metadata requires a source")
    wind = np.asarray(curves.get("wind_nodes_ms", []), dtype=float)
    if wind.ndim != 1 or len(wind) < 2 or not np.isfinite(wind).all() or wind[0] != 0 or (np.diff(wind) <= 0).any():
        raise ValueError("Wind nodes must start at zero and strictly increase")
    damage = curves.get("damage_nodes", {})
    if not isinstance(damage, dict) or not damage:
        raise ValueError("At least one construction damage curve is required")
    for kind, nodes in damage.items():
        nodes = np.asarray(nodes, dtype=float)
        if not kind.strip() or nodes.shape != wind.shape or not np.isfinite(nodes).all() or (nodes < 0).any() or (nodes > 1).any() or (np.diff(nodes) < 0).any() or nodes[0] != 0:
            raise ValueError(f"Invalid damage curve for {kind!r}: require monotone ratios in [0,1], starting at zero")
        damage[kind] = nodes
    return {"wind_nodes_ms": wind, "damage_nodes": damage, "metadata": metadata}


def validate_portfolio(portfolio, constructions):
    required = ["construction", "replacement_value_usd", "deductible_fraction", "limit_fraction"]
    missing = set(required) - set(portfolio.columns)
    if missing or portfolio.empty:
        raise ValueError(f"Empty portfolio or missing columns: {sorted(missing)}")
    unknown = set(portfolio.construction) - set(constructions)
    if unknown:
        raise ValueError(f"Unknown construction types: {sorted(map(str, unknown))}")
    for key in required[1:]:
        values = portfolio[key].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(f"{key} must be finite and nonnegative")
    if (portfolio.replacement_value_usd <= 0).any():
        raise ValueError("Replacement values must be positive")
    if (portfolio[["deductible_fraction", "limit_fraction"]] > 1).any().any():
        raise ValueError("Deductibles and limits must be fractions in [0,1]")


def load_portfolio(path, vulnerability):
    p = pd.read_csv(path, dtype={"property_id": str}, keep_default_na=False)
    required = {"property_id", "lat", "lon", "construction", "replacement_value_usd",
                "deductible_fraction", "limit_fraction"}
    if not required.issubset(p.columns):
        raise ValueError(f"Portfolio missing columns: {sorted(required - set(p.columns))}")
    for key in ["lat", "lon", "replacement_value_usd", "deductible_fraction", "limit_fraction"]:
        p[key] = pd.to_numeric(p[key], errors="raise")
    if p.property_id.str.strip().eq("").any() or p.property_id.duplicated().any():
        raise ValueError("Property IDs must be nonempty and unique")
    if not (p.lat.between(-90, 90) & p.lon.between(-180, 180)).all():
        raise ValueError("Invalid property coordinates")
    validate_portfolio(p, vulnerability["damage_nodes"])
    return p
