"""Run with python -m hurricane_risk --help."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys

os.environ.setdefault("MPLCONFIGDIR", "/tmp/hurricane-risk-matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

from .model import (NOAA_URL, DAMAGE_NODES, WIND_NODES, read_hurdat, synthetic_portfolio,
                    hazard_catalog, property_losses, annual_losses, sample_annual_blocks,
                    ep_curve, loss_metrics)


def validate_config(cfg):
    for key in ["properties", "interpolation_minutes", "uncertainty_replicates", "simulation_years"]:
        if not isinstance(cfg[key], int) or cfg[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    if cfg["uncertainty_replicates"] < 20:
        raise ValueError("Use at least 20 uncertainty replicates (200+ recommended)")
    if cfg["end_year"] < cfg["start_year"]:
        raise ValueError("end_year must be >= start_year")
    for key in ["rmw_km", "rankine_alpha", "land_exposure_factor"]:
        if not np.isfinite(cfg[key]) or cfg[key] <= 0:
            raise ValueError(f"{key} must be finite and positive")
    if cfg["land_exposure_factor"] > 1:
        raise ValueError("land_exposure_factor must be <= 1")
    n_years = cfg["end_year"] - cfg["start_year"] + 1
    if not cfg["return_periods"] or any(p <= 1 or p > n_years for p in cfg["return_periods"]):
        raise ValueError("Return periods must exceed 1 and not exceed catalog length")
    scenarios = cfg["scenarios"]
    if not scenarios or scenarios[0] != {"name": "historical", "wind_multiplier": 1., "frequency_multiplier": 1.}:
        raise ValueError("First scenario must be historical with both multipliers 1")
    if len({s["name"] for s in scenarios}) != len(scenarios):
        raise ValueError("Scenario names must be unique")
    for s in scenarios:
        for key in ["wind_multiplier", "frequency_multiplier"]:
            if not np.isfinite(s[key]) or s[key] <= 0:
                raise ValueError(f"{key} must be finite and positive")


def download(path, url):
    if not url.startswith("https://"):
        raise ValueError("Track URL must use HTTPS")
    try:
        response = requests.get(url, timeout=120)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError("NOAA download failed. Download the HURDAT2 file on a network-enabled "
                           "machine and pass --tracks PATH, or use --demo for synthetic validation.") from exc
    temporary = path.with_suffix(".download")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(response.text)
    try:
        read_hurdat(temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def demo_tracks(cfg):
    """Fabricated HURDAT2-format records exclusively for offline integration runs."""
    rng = np.random.default_rng(cfg["seed"] + 1)
    lines = []
    for year in range(cfg["start_year"], cfg["end_year"] + 1):
        for j in range(rng.poisson(4)):
            lines.append(f"AL{j+1:02d}{year}, SYNTHETIC, 17,")
            land_lon = rng.uniform(-89, -78)
            latitude = rng.uniform(24, 30)
            peak = rng.uniform(65, 150)
            for k, time in enumerate(pd.date_range(f"{year}-09-01", periods=17, freq="6h")):
                lat = latitude + (k-8)*.35
                lon = land_lon + (k-8)*.24
                wind = max(35, peak - abs(k-8)*4)
                fields = [time.strftime("%Y%m%d"), time.strftime("%H%M"), "", "HU" if wind >= 64 else "TS",
                          f"{lat:.2f}N", f"{abs(lon):.2f}W", f"{wind:.0f}", "980"]
                lines.append(", ".join(fields + ["-999"] * 13) + ",")
    return "\n".join(lines) + "\n"


def simulate_scenarios(events, hazard, portfolio, cfg, out):
    years = np.arange(cfg["start_year"], cfg["end_year"] + 1)
    rng = np.random.default_rng(cfg["seed"] + 2)
    scenarios = cfg["scenarios"]
    n_sim = cfg["simulation_years"]
    slots = int(np.floor(max(s["frequency_multiplier"] for s in scenarios))) + 1
    # Shared random numbers pair scenarios and reduce comparison simulation noise.
    indices = rng.integers(0, len(years), (n_sim, slots))
    uniforms = rng.random(n_sim)
    annual_catalog, point_metrics, annual_sim, event_tables = {}, {}, {}, []
    for s in scenarios:
        name = s["name"]
        ground, insured = property_losses(hazard[:, 1, :] * s["wind_multiplier"], portfolio)
        totals = insured.sum(axis=1)
        agg, occ = annual_losses(totals, events.year, years)
        annual_catalog[name] = (agg, occ)
        sim_agg, sim_occ = sample_annual_blocks(agg, occ, indices, uniforms, s["frequency_multiplier"])
        annual_sim[name] = (sim_agg, sim_occ)
        metrics = loss_metrics(sim_agg, sim_occ, cfg["return_periods"])
        # Exact expectation avoids Monte Carlo error in AAL.
        metrics["aal_usd"] = float(agg.mean() * s["frequency_multiplier"])
        point_metrics[name] = metrics
        table = events.assign(scenario=name, ground_up_usd=ground.sum(axis=1), insured_usd=totals)
        event_tables.append(table)
        if name == "historical":
            pd.DataFrame({"year": years, "aggregate_insured_usd": agg,
                          "occurrence_insured_usd": occ}).to_csv(out / "historical_annual_losses.csv", index=False)
            empirical = []
            for kind, values in [("AEP", agg), ("OEP", occ)]:
                thresholds = np.unique(np.r_[0., values])
                empirical.extend({"kind": kind, "loss_usd": x, "exceedance_probability": p}
                                 for x, p in zip(thresholds, ep_curve(values, thresholds)))
            pd.DataFrame(empirical).to_csv(out / "historical_empirical_ep.csv", index=False)
            pd.DataFrame({"property_id": portfolio.property_id,
                          "ground_up_aal_usd": ground.sum(axis=0) / len(years),
                          "insured_aal_usd": insured.sum(axis=0) / len(years)}).to_csv(
                              out / "property_aal.csv", index=False)
    pd.concat(event_tables).to_csv(out / "event_losses.csv", index=False)
    pd.DataFrame(point_metrics).T.rename_axis("scenario").to_csv(out / "summary.csv")
    pd.DataFrame([{"simulation_year": i+1, "scenario": name,
                   "aggregate_insured_usd": a, "occurrence_insured_usd": o}
                  for name, (agg, occ) in annual_sim.items()
                  for i, (a, o) in enumerate(zip(agg, occ))]).to_csv(out / "simulated_annual_losses.csv", index=False)

    # Fixed thresholds make bands comparable across parameter draws.
    top = max(float(a.max()) for a, _ in annual_sim.values())
    thresholds = np.linspace(0, max(top, 1) * 1.3, 151)
    rows, curves = [], []
    for name, (agg, occ) in annual_sim.items():
        for kind, vals in [("AEP", agg), ("OEP", occ)]:
            curves.extend({"scenario": name, "kind": kind, "loss_usd": x, "exceedance_probability": p}
                          for x, p in zip(thresholds, ep_curve(vals, thresholds)))
    pd.DataFrame(curves).to_csv(out / "ep_curves.csv", index=False)

    draws = []
    # Separate finite-catalog and assumed model uncertainty, plus their combination.
    for mode in ["sampling", "model", "combined"]:
        for rep in range(cfg["uncertainty_replicates"]):
            boot = rng.integers(0, len(years), len(years)) if mode != "model" else np.arange(len(years))
            if mode != "sampling":
                size_index = int(rng.choice(3, p=[.25, .5, .25]))
                intensity = float(rng.lognormal(-.5 * .05**2, .05))
                vulnerability = float(rng.lognormal(-.5 * .20**2, .20))
            else:
                size_index, intensity, vulnerability = 1, 1., 1.
            draws.append({"mode": mode, "replicate": rep, "rmw_multiplier": [.8, 1, 1.2][size_index],
                          "intensity_multiplier": intensity, "vulnerability_multiplier": vulnerability})
            for s in scenarios:
                _, insured = property_losses(hazard[:, size_index, :] * s["wind_multiplier"] * intensity,
                                              portfolio, vulnerability)
                agg, occ = annual_losses(insured.sum(axis=1), events.year, years)
                a, o = sample_annual_blocks(agg[boot], occ[boot], indices, uniforms, s["frequency_multiplier"])
                metrics = loss_metrics(a, o, cfg["return_periods"])
                metrics["aal_usd"] = float(agg[boot].mean() * s["frequency_multiplier"])
                rows.append({"mode": mode, "replicate": rep, "scenario": s["name"], **metrics})
        print(f"Completed {mode} uncertainty ({cfg['uncertainty_replicates']} replicates)", flush=True)
    samples = pd.DataFrame(rows)
    samples.to_csv(out / "uncertainty_samples.csv", index=False)
    pd.DataFrame(draws).to_csv(out / "parameter_draws.csv", index=False)
    metric_cols = list(point_metrics["historical"])
    bounds = []
    comparisons = []
    for (mode, name), group in samples.groupby(["mode", "scenario"]):
        base = samples[(samples["mode"] == mode) & (samples.scenario == "historical")].set_index("replicate")
        group = group.set_index("replicate")
        for metric in metric_cols:
            q = group[metric].quantile([.05, .5, .95]).to_numpy()
            bounds.append({"mode": mode, "scenario": name, "metric": metric,
                           "point": point_metrics[name][metric], "p05": q[0], "p50": q[1], "p95": q[2]})
            delta = group[metric] - base[metric]
            pct = 100 * delta / base[metric].replace(0, np.nan)
            d = delta.quantile([.05, .5, .95]).to_numpy()
            p = pct.quantile([.05, .5, .95]).to_numpy()
            base_point = point_metrics["historical"][metric]
            change = point_metrics[name][metric] - base_point
            comparisons.append({"mode": mode, "scenario": name, "metric": metric,
                                "delta_point_usd": change, "delta_p05_usd": d[0],
                                "delta_p50_usd": d[1], "delta_p95_usd": d[2],
                                "percent_point": 100*change/base_point if base_point else np.nan,
                                "percent_p05": p[0], "percent_p50": p[1], "percent_p95": p[2],
                                "percent_valid_replicates": int(pct.notna().sum())})
    pd.DataFrame(bounds).to_csv(out / "uncertainty_intervals.csv", index=False)
    pd.DataFrame(comparisons).to_csv(out / "scenario_comparison.csv", index=False)
    return point_metrics, pd.DataFrame(curves), pd.DataFrame(bounds)


def plots(portfolio, curves, intervals, out, demo):
    label = "SYNTHETIC DEMO — " if demo else ""
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    axes[0].scatter(portfolio.lon, portfolio.lat, s=portfolio.replacement_value_usd / 15000, alpha=.5)
    axes[0].set(xlabel="Longitude", ylabel="Latitude", title="Synthetic Florida portfolio")
    axes[0].set_aspect(1 / np.cos(np.deg2rad(27)))
    for kind, ax in zip(["OEP", "AEP"], axes[1:]):
        for name, g in curves[curves.kind == kind].groupby("scenario", sort=False):
            ax.plot(g.loss_usd / 1e6, g.exceedance_probability, label=name)
        ax.set(xlabel="Annual insured loss (USD millions)", ylabel="P(annual loss > x)", title=kind, ylim=(0, 1))
        ax.grid(alpha=.2)
    axes[2].legend(fontsize=7)
    fig.suptitle(label + "Wind-only hurricane loss stress tests")
    fig.tight_layout()
    fig.savefig(out / "portfolio_and_ep.png", dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 5))
    g = intervals[(intervals["mode"] == "combined") & (intervals.metric == "aal_usd")]
    x = np.arange(len(g))
    ax.vlines(x, g.p05 / 1e6, g.p95 / 1e6, color="C0", lw=3, label="5–95% combined range")
    ax.scatter(x, g.p50 / 1e6, marker="o", label="Replicate median")
    ax.scatter(x, g.point / 1e6, marker="x", color="black", label="Nominal estimate")
    ax.set(xticks=x, xticklabels=g.scenario, ylabel="AAL (USD millions)", title=label + "AAL uncertainty")
    ax.tick_params(axis="x", labelsize=8)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "aal_uncertainty.png", dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots()
    for name, nodes in DAMAGE_NODES.items():
        ax.plot(WIND_NODES, nodes, marker="o", label=name)
    ax.set(xlabel="1-minute sustained wind at 10 m (m/s)", ylabel="Mean damage ratio",
           title="Explicitly assumed vulnerability curves", ylim=(0, 1))
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "vulnerability.png", dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--tracks", type=Path, default=Path("data/hurdat2-1851-2024-040425.txt"))
    parser.add_argument("--download", action="store_true", help="Download pinned NOAA data if absent")
    parser.add_argument("--url", default=NOAA_URL)
    parser.add_argument("--demo", action="store_true", help="Use FABRICATED tracks; never historical estimates")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    validate_config(cfg)
    out = args.out or Path("outputs/demo" if args.demo else "outputs/historical")
    out.mkdir(parents=True, exist_ok=True)
    if args.demo:
        track_path = out / "SYNTHETIC_tracks.txt"
        track_path.write_text(demo_tracks(cfg))
    else:
        track_path = args.tracks
        if not track_path.exists() and args.download:
            download(track_path, args.url)
        if not track_path.exists():
            parser.error("Track file missing. Use --download, --tracks PATH, or --demo.")
    tracks = read_hurdat(track_path)
    if tracks.season.min() > cfg["start_year"] or tracks.season.max() < cfg["end_year"]:
        raise ValueError("Input does not span requested years; provide a complete catalog, not a storm subset")
    selected = tracks[tracks.season.between(cfg["start_year"], cfg["end_year"])]
    ids = selected.loc[selected.status == "HU", "storm_id"].unique()
    selected = selected[selected.storm_id.isin(ids)]
    if selected.vmax_ms.isna().any():
        raise ValueError("Selected hurricane tracks contain missing maximum winds; supply a complete "
                         "catalog or explicitly resolve missing intensities before modeling")
    portfolio = synthetic_portfolio(cfg["properties"], cfg["seed"])
    portfolio.to_csv(out / "portfolio.csv", index=False)
    pd.DataFrame({"wind_ms": WIND_NODES, **DAMAGE_NODES}).to_csv(out / "assumed_vulnerability.csv", index=False)
    print(f"{'SYNTHETIC DEMO' if args.demo else 'HISTORICAL CATALOG'}: {len(ids)} storms, "
          f"{len(portfolio)} properties; computing wind fields", flush=True)
    events, hazard = hazard_catalog(selected, portfolio, cfg)
    np.savez_compressed(out / "hazard.npz", wind_ms=hazard,
                        storm_id=events.storm_id.to_numpy(dtype=str),
                        property_id=portfolio.property_id.to_numpy(dtype=str), rmw_multipliers=[.8, 1, 1.2])
    metrics, curves, intervals = simulate_scenarios(events, hazard, portfolio, cfg, out)
    plots(portfolio, curves, intervals, out, args.demo)
    manifest = {
        "data_kind": "FABRICATED DEMO; NOT HISTORICAL" if args.demo else "NOAA HURDAT2 user-supplied or downloaded catalog",
        "track_path": str(track_path.resolve()), "download_url": args.url if args.download and not args.demo else None,
        "track_sha256": hashlib.sha256(track_path.read_bytes()).hexdigest(),
        "config": cfg, "total_insured_value_usd": float(portfolio.replacement_value_usd.sum()),
        "storms": len(events), "years_including_zero_loss": cfg["end_year"]-cfg["start_year"]+1,
        "input_season_span": [int(tracks.season.min()), int(tracks.season.max())],
        "rmw_missing_fraction": float(selected.rmw_km.isna().mean()),
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
                     "matplotlib": matplotlib.__version__},
        "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    lines = ["# " + manifest["data_kind"], "", f"Portfolio replacement value: ${manifest['total_insured_value_usd']:,.0f}.",
             "", "| Scenario | Insured AAL | Combined 5–95% range |", "|---|---:|---:|"]
    for name, m in metrics.items():
        bound = intervals[(intervals.scenario == name) & (intervals["mode"] == "combined") & (intervals.metric == "aal_usd")].iloc[0]
        lines.append(f"| {name} | ${m['aal_usd']:,.0f} | ${bound.p05:,.0f}–${bound.p95:,.0f} |")
    lines += ["", "These are wind-only, assumed-model estimates. Alternative scenarios are sensitivity tests, not climate projections.",
              "Ranges combine annual block resampling with assumed wind, storm-size and vulnerability uncertainty; they are not calibrated confidence bounds.",
              "EP CSVs use strict exceedance; return losses are generalized inverse empirical CDF quantiles.",
              "The simulated years recycle this finite catalog and add no new tail information. See README.md for equations and limitations."]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print(f"Results written to {out.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
