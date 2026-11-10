"""External station-peak evaluation: python -m hurricane_risk.validation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/hurricane-risk-matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .model import (KNOT_TO_MS, read_hurdat, hazard_catalog, synthetic_portfolio,
                    property_losses, annual_losses, loss_metrics)
from .__main__ import validate_config
from .inputs import load_portfolio, load_vulnerability
from .artifacts import output_directory, output_hashes


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_observations(path, sources):
    obs = pd.read_csv(path, keep_default_na=False)
    if obs.duplicated(["storm_id", "station_id"]).any():
        raise ValueError("Duplicate storm/station observations")
    obs["sustained_kt"] = pd.to_numeric(obs.sustained_kt.replace("", np.nan))
    if not obs.incomplete.isin([0, 1]).all():
        raise ValueError("incomplete must be 0 or 1")
    for _, row in obs.iterrows():
        src = sources["sources"][row.source_id]
        if src["storm_id"] != row.storm_id:
            raise ValueError("Observation source/storm mismatch")
        time = pd.Timestamp(row.peak_time_utc)
        if not pd.Timestamp(src["window_start"]) <= time <= pd.Timestamp(src["window_end"]):
            raise ValueError("Observation peak outside event window")
    if not (obs.lat.between(-90, 90) & obs.lon.between(-180, 180)).all():
        raise ValueError("Invalid station coordinates")
    finite = obs.sustained_kt.notna()
    if not obs.loc[finite, "sustained_kt"].between(1, 250).all():
        raise ValueError("Invalid sustained wind")
    obs["observed_ms"] = obs.sustained_kt * KNOT_TO_MS
    obs["primary"] = finite & (obs.incomplete == 0) & obs.metadata_issue.eq("")
    obs["exclusion_reason"] = np.select(
        [~finite, obs.metadata_issue.ne(""), obs.incomplete.eq(1)],
        ["missing_sustained_wind", np.where(obs.metadata_issue.str.contains('coordinate|longitude', case=False),
                                          "suspect_coordinates", "incompatible_or_unverified_metadata"),
         "incomplete_peak_lower_bound"],
        default="eligible_no_incomplete_flag")
    return obs


def footprint_predictions(obs, tracks, sources, cfg):
    """Use the production wind engine, with one regional event window per source."""
    result = obs.copy()
    for col in ["modeled_ms", "rmw_low_ms", "rmw_high_ms", "fine_step_ms"]:
        result[col] = np.nan
    for source_id, stations in obs.groupby("source_id"):
        src = sources["sources"][source_id]
        tr = tracks[(tracks.storm_id == src["storm_id"]) &
                    tracks.time.between(src["window_start"], src["window_end"])]
        if len(tr) < 2 or tr.vmax_ms.isna().any():
            raise ValueError(f"Missing or unusable validation track {src['storm_id']}")
        _, winds = hazard_catalog(tr, stations, cfg)
        result.loc[stations.index, "rmw_low_ms"] = winds[0, 0]
        result.loc[stations.index, "modeled_ms"] = winds[0, 1]
        result.loc[stations.index, "rmw_high_ms"] = winds[0, 2]
        fine_cfg = {**cfg, "interpolation_minutes": min(5, cfg["interpolation_minutes"])}
        _, fine = hazard_catalog(tr, stations, fine_cfg)
        result.loc[stations.index, "fine_step_ms"] = fine[0, 1]
    return result


def scores(observed, modeled):
    observed, modeled = np.asarray(observed), np.asarray(modeled)
    error = modeled - observed
    correlation = (np.corrcoef(observed, modeled)[0, 1]
                   if len(observed) > 2 and observed.std() > 0 and modeled.std() > 0 else np.nan)
    return {"n": len(error), "bias_ms": float(error.mean()),
            "mae_ms": float(np.abs(error).mean()), "rmse_ms": float(np.sqrt(np.mean(error**2))),
            "correlation": float(correlation)}


def correction_factor(frame):
    """Storm-balanced log-ratio fit; no storm gets extra weight for more stations."""
    if frame.empty or (frame.modeled_ms <= 0).any():
        raise ValueError("Need positive modeled winds for correction factor")
    log_ratio = np.log(frame.observed_ms / frame.modeled_ms)
    return float(np.exp(log_ratio.groupby(frame.storm_id).mean().mean()))


def leave_one_storm_out(primary):
    result = primary.copy()
    result["loeo_factor"] = np.nan
    for storm in primary.storm_id.unique():
        train = primary[primary.storm_id != storm]
        if train.storm_id.nunique() < 2:
            raise ValueError("At least three storms required for leave-one-storm-out evaluation")
        result.loc[result.storm_id == storm, "loeo_factor"] = correction_factor(train)
    result["loeo_corrected_ms"] = result.modeled_ms * result.loeo_factor
    return result


def bootstrap_metrics(primary, replicates, seed):
    """Storm-block bootstrap; duplicate sampled storms retain their entire rows."""
    rng = np.random.default_rng(seed)
    storms = primary.storm_id.unique()
    rows = []
    for rep in range(replicates):
        chosen = rng.choice(storms, len(storms), replace=True)
        groups = [primary[primary.storm_id == sid] for sid in chosen]
        sample = pd.concat(groups, ignore_index=True)
        # Average sampled storm log-ratios, preserving duplicate storm draws.
        factor = float(np.exp(np.mean([np.log(g.observed_ms/g.modeled_ms).mean() for g in groups])))
        rows.append({"replicate": rep, **scores(sample.observed_ms, sample.modeled_ms),
                     "wind_correction_factor": factor})
    return pd.DataFrame(rows)


def uncertainty_bands(pairs, seed, exposure_factor):
    """Prior model envelope from existing size/intensity assumptions, not fitted residuals."""
    rng = np.random.default_rng(seed)
    size = rng.choice(3, 10000, p=[.25, .5, .25])
    intensity = rng.lognormal(-.5 * .05**2, .05, len(size))
    wind = pairs[["rmw_low_ms", "modeled_ms", "rmw_high_ms"]].to_numpy()
    draws = wind[:, size] * intensity[None, :]
    pairs = pairs.copy()
    pairs["prior_p05_ms"], pairs["prior_p95_ms"] = np.quantile(draws, [.05, .95], axis=1)
    pairs["within_prior_90pct"] = pairs.observed_ms.between(pairs.prior_p05_ms, pairs.prior_p95_ms)
    pairs["residual_ms"] = pairs.modeled_ms - pairs.observed_ms
    pairs["open_exposure_ms"] = pairs.modeled_ms / exposure_factor
    return pairs


def loss_implications(tracks, cfg, factors, out, portfolio=None, vulnerability=None):
    """Transport a global wind-bias sensitivity through existing insurance terms."""
    selected = tracks[tracks.season.between(cfg["start_year"], cfg["end_year"])]
    ids = selected.loc[selected.status == "HU", "storm_id"].unique()
    selected = selected[selected.storm_id.isin(ids)]
    if portfolio is None:
        portfolio = synthetic_portfolio(cfg["properties"], cfg["seed"])
    events, hazard = hazard_catalog(selected, portfolio, cfg)
    years = np.arange(cfg["start_year"], cfg["end_year"] + 1)
    rows = []
    for label, factor in factors.items():
        ground, insured = property_losses(hazard[:, 1, :] * factor, portfolio, vulnerability=vulnerability)
        agg, occ = annual_losses(insured.sum(axis=1), events.year, years)
        metrics = loss_metrics(agg, occ, cfg["return_periods"])
        rows.append({"case": label, "wind_factor": factor, "ground_up_aal_usd": ground.sum()/len(years), **metrics})
    frame = pd.DataFrame(rows)
    base = frame.loc[frame["case"] == "nominal", "aal_usd"].iloc[0]
    frame["aal_change_pct"] = 100 * (frame.aal_usd/(base if base else np.nan) - 1)
    frame.to_csv(out / "insured_loss_sensitivity.csv", index=False)
    return frame


def diagnostic_plot(pairs, loeo, losses, out):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    p = pairs[pairs.primary]
    for sid, g in p.groupby("storm_id"):
        axes[0].scatter(g.observed_ms, g.modeled_ms, label=sid, s=30)
        axes[0].vlines(g.observed_ms, g.prior_p05_ms, g.prior_p95_ms, alpha=.25)
    limit = max(p.observed_ms.max(), p.prior_p95_ms.max()) * 1.08
    axes[0].plot([0, limit], [0, limit], "k--", lw=1)
    axes[0].set(xlim=(0, limit), ylim=(0, limit), xlabel="Observed 2-min sustained wind (m/s)",
                ylabel="Modeled 1-min peak (m/s)", title="Eligible station peaks; prior 90% bars")
    axes[0].legend(fontsize=7)
    for sid, g in loeo.groupby("storm_id"):
        axes[1].scatter(g.observed_ms, g.loeo_corrected_ms-g.observed_ms, label=sid, s=30)
    axes[1].axhline(0, color="k", ls="--", lw=1)
    axes[1].set(xlabel="Observed sustained wind (m/s)", ylabel="Held-out corrected error (m/s)",
                title="Leave-one-storm-out bias correction")
    axes[2].bar(np.arange(len(losses)), losses.aal_usd/1e6, color="C0")
    axes[2].set(xticks=np.arange(len(losses)), xticklabels=losses["case"], ylabel="Insured AAL (USD millions)",
                title="Conditional wind-factor loss sensitivity")
    axes[2].tick_params(axis="x", labelrotation=30, labelsize=7)
    fig.tight_layout()
    fig.savefig(out / "validation_diagnostics.png", dpi=170)
    plt.close(fig)


def footprint_plot(pairs, tracks, sources, cfg, out):
    """Geographic peak-wind contours with observed peaks on the same color scale."""
    from matplotlib.lines import Line2D
    from matplotlib.colors import Normalize
    from matplotlib.cm import ScalarMappable
    fig, axes = plt.subplots(1, len(sources["sources"]), figsize=(15, 5), squeeze=False)
    scale = Normalize(0, 70)
    for ax, (source_id, src) in zip(axes[0], sources["sources"].items()):
        stations = pairs[pairs.source_id == source_id]
        x = np.linspace(stations.lon.min()-.3, stations.lon.max()+.3, 60)
        y = np.linspace(stations.lat.min()-.3, stations.lat.max()+.3, 60)
        xx, yy = np.meshgrid(x, y)
        grid = pd.DataFrame({"lat": yy.ravel(), "lon": xx.ravel()})
        tr = tracks[(tracks.storm_id == src["storm_id"]) &
                    tracks.time.between(src["window_start"], src["window_end"])]
        _, wind = hazard_catalog(tr, grid, cfg)
        ax.contourf(xx, yy, wind[0, 1].reshape(xx.shape), levels=np.arange(0, 75, 5),
                    cmap="viridis", norm=scale, extend="max")
        ax.plot(tr.lon, tr.lat, color="white", lw=1, alpha=.6)
        for flag, marker in [(True, "o"), (False, "^")]:
            g = stations[stations.primary.eq(flag) & stations.observed_ms.notna() & stations.metadata_issue.eq("")]
            ax.scatter(g.lon, g.lat, c=g.observed_ms, cmap="viridis", norm=scale,
                       marker=marker, edgecolors="black", s=55, zorder=3)
        bad = stations[stations.metadata_issue.ne("") | stations.observed_ms.isna()]
        ax.scatter(bad.lon, bad.lat, marker="x", color="red", s=35, zorder=4)
        ax.set(xlim=(x[0], x[-1]), ylim=(y[0], y[-1]), xlabel="Longitude", ylabel="Latitude", title=src["name"])
        ax.set_aspect(1/np.cos(np.deg2rad(stations.lat.mean())))
    handles = [Line2D([], [], marker="o", ls="", color="black", label="Eligible observed peak"),
               Line2D([], [], marker="^", ls="", color="black", label="Incomplete observed lower bound"),
               Line2D([], [], marker="x", ls="", color="red", label="Suspect metadata / missing wind")]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=8)
    fig.suptitle("Modeled peak footprints (background) and station observations (markers); no basemap")
    fig.subplots_adjust(bottom=.19, top=.85, wspace=.35, right=.87)
    colorbar_ax = fig.add_axes([.91, .25, .015, .5])
    fig.colorbar(ScalarMappable(norm=scale, cmap="viridis"), cax=colorbar_ax, label="Sustained wind (m/s)")
    fig.savefig(out / "observed_footprints.png", dpi=170)
    plt.close(fig)


def write_report(pairs, metric_table, boot, loeo, losses, sources, cfg, out, factor):
    primary = pairs[pairs.primary]
    raw = scores(primary.observed_ms, primary.modeled_ms)
    cv = scores(loeo.observed_ms, loeo.loeo_corrected_ms)
    q = boot[["bias_ms", "mae_ms", "rmse_ms", "wind_correction_factor"]].quantile([.05, .95])
    coverage = 100 * primary.within_prior_90pct.mean()
    incomplete = pairs[(pairs.incomplete == 1) & pairs.observed_ms.notna() & pairs.metadata_issue.eq("")]
    violations = int((incomplete.modeled_ms < incomplete.observed_ms).sum())
    text = ["# Hurricane wind footprint validation", "",
            f"**Finding.** The unchanged Rankine model overpredicts eligible reported station peaks "
            f"by {raw['bias_ms']:.1f} m/s on average (RMSE {raw['rmse_ms']:.1f} m/s); its assumed "
            f"90% wind envelope covers {coverage:.0f}% of observations. This external comparison "
            "reveals poor agreement but cannot certify an independently withheld wind field. "
            "The damaging hurricane-force core remains unvalidated.", "",
            "## Data and comparability", "",
            f"All {len(pairs)} unique METAR rows from three preselected NWS regional reports are retained: "
            f"Irma (2017), Michael (2018), and Ian (2022). {len(primary)} station/event pairs have a finite "
            "sustained wind, no incomplete flag, and no flagged coordinate issue; only these enter primary scores. "
            "Selection uses report membership and quality flags, never the model residual. One duplicate KRSW "
            "entry in Irma is removed. All excluded rows and reasons remain in `station_pairs.csv`.", "",
            "The reports specify 10-m, two-minute sustained winds in knots. The model predicts one-minute "
            "sustained winds; conversion to m/s is 0.514444. Following NOAA's duration guidance, the nominal "
            "comparison uses no 1-to-2-minute conversion. A hypothetical +5% adjustment of observations is "
            "reported separately as duration sensitivity, not a published conversion. Gusts, marine sites, "
            "and unknown-height non-METAR measurements are excluded. The same production wind engine and "
            "configured 0.85 exposure factor are used at station coordinates; regional UTC passage windows "
            "are listed in the provenance JSON. This evaluates peak amplitude at sparse locations, not a "
            "complete two-dimensional footprint, gust field, time evolution, or peak timing.", "",
            f"Eligible observed peaks span {primary.observed_ms.min():.1f}–{primary.observed_ms.max():.1f} "
            "m/s, all below the 64-kt hurricane threshold. The excluded and censored records contain "
            "the strongest measurements, so primary scores cannot establish performance where the "
            "vulnerability curves generate the most damage.", "",
            "These observations were not used to select the original model coefficients. However, NHC may "
            "have used the same station data in HURDAT2 intensity analysis. Independence from best-track "
            "construction cannot be established; leave-one-storm-out fitting below only prevents leakage "
            "in the new multiplicative correction. All three storms are development diagnostics, not an "
            "untouched future test set.", "", "## Performance", "",
            "Errors are modeled minus observed wind, in m/s. Correlation measures association, not agreement. "
            "The open-exposure diagnostic divides the nominal wind by 0.85 without fitting, since airport "
            "exposure differs from insured properties. No model coefficient is changed by this validation.", "",
            "| Sample / comparison | n | Bias | MAE | RMSE | Correlation |", "|---|---:|---:|---:|---:|---:|"]
    for _, row in metric_table.iterrows():
        text.append(f"| {row['sample']} / {row['comparison']} | {int(row['n'])} | {row.bias_ms:.2f} | "
                    f"{row.mae_ms:.2f} | {row.rmse_ms:.2f} | {row.correlation:.2f} |")
    text += ["", "The `pooled_without_Ian` row is a report-quality sensitivity: it omits "
             "the entire Ian product because that preliminary summary documents widespread outages. "
             "This tests whether the result depends only on unflagged Ian rows; it is not an alternative "
             "primary sample selected by error size.", "", "## Uncertainty and transfer test", "",
             f"Resampling whole storms with replacement (2,000 replicates, seeded) gives descriptive "
             f"5–95% ranges: bias {q.loc[.05,'bias_ms']:.2f} to {q.loc[.95,'bias_ms']:.2f} m/s, "
             f"MAE {q.loc[.05,'mae_ms']:.2f} to {q.loc[.95,'mae_ms']:.2f}, and "
             f"RMSE {q.loc[.05,'rmse_ms']:.2f} to {q.loc[.95,'rmse_ms']:.2f}. "
             "With only three storms there are very few independent blocks; these coarse ranges are not "
             "well-calibrated population confidence intervals. Repeated stations across storms create "
             "additional dependence that this storm-only bootstrap does not resolve.", "",
             f"The original assumed model envelope (RMW ×0.8/1.0/1.2 with weights .25/.50/.25, "
             f"mean-one lognormal intensity with log SD .05) contains {coverage:.1f}% of eligible "
             "observations in its nominal 90% interval. This is an ensemble of model-parameter assumptions, "
             "not a predictive interval including observation error or structural discrepancy. Its "
             "coverage diagnoses the adequacy of the prior wind uncertainty only; vulnerability uncertainty "
             "does not affect wind validation. The 5-minute time-step check changes eligible nominal peaks "
             f"by at most {np.max(np.abs(primary.fine_step_ms-primary.modeled_ms)):.2f} m/s.", "",
             f"A storm-balanced geometric-mean observed/model ratio is {factor:.3f}; its three-storm "
             f"bootstrap factor range is {q.loc[.05,'wind_correction_factor']:.3f}–"
             f"{q.loc[.95,'wind_correction_factor']:.3f}. For each held-out storm, a factor fitted only to "
             "the other two storms is applied to its station predictions. Held-out pooled RMSE is "
             f"{cv['rmse_ms']:.2f} m/s versus nominal {raw['rmse_ms']:.2f} m/s. "
             "A global correction cannot fix storm-size errors, asymmetry, station-specific exposure, "
             "or premature sensor failure. It remains diagnostic and is not installed as a calibrated model.", "",
             f"There are {len(incomplete)} finite, metadata-eligible incomplete station peaks, treated only "
             f"as lower bounds: the model maximum falls below {violations} of them. Model excess above "
             "an incomplete peak is not evidence of overprediction. Irma KFMY and Ian KVDF coordinates "
             "are flagged as suspect rather than silently corrected. Ian report remarks identify more "
             "incomplete stations than individual row flags. Unflagged rows can still have outages or "
             "report errors; the strongest near-eye winds are especially underrepresented in primary scores.", "",
             "## Implications for insured losses", "",
             f"The configured {cfg['start_year']}–{cfg['end_year']} catalog, portfolio, "
             "vulnerability curves, deductibles and limits are rerun with global wind multipliers. "
             "Below, `empirical_p05/p95` are the wind-factor bootstrap endpoints and `empirical_fit` "
             "uses all eligible observations. These are conditional transport sensitivities, not "
             "validated loss corrections or total loss uncertainty bounds. Return losses use exact "
             "annual empirical CDFs here (the main workflow uses resampled years for scenario EPs).", "",
             "| Wind sensitivity | Multiplier | Insured AAL | Change | 20-year OEP loss | 20-year AEP loss |",
             "|---|---:|---:|---:|---:|---:|"]
    for _, row in losses.iterrows():
        # Default report uses the largest configured period, labeled dynamically below.
        period = max(cfg["return_periods"])
        text.append(f"| {row['case']} | {row.wind_factor:.3f} | ${row.aal_usd:,.0f} | {row.aal_change_pct:+.1f}% | "
                    f"${row[f'oep_{period:g}yr_usd']:,.0f} | ${row[f'aep_{period:g}yr_usd']:,.0f} |")
    if max(cfg["return_periods"]) != 20:
        text = [s.replace("20-year", f"{max(cfg['return_periods']):g}-year") for s in text]
    text += ["", "Nonlinear damage curves and deductibles amplify wind errors: a wind-bias adjustment "
             "must be passed through property damage and policy terms, not multiplied directly into AAL. "
             "The empirical factor combines wind structure, airport exposure and observation deficiencies; "
             "transporting it to residential properties over 45 years is unverified. The original loss "
             "model remains unchanged, and its 5% log-SD wind uncertainty assumption should not be interpreted "
             "as validated by this experiment.", "", "## Limitations and next scientific step", "",
             "The narrow sample spans only three regional landfalls and sparse airport locations, with "
             "many high-wind instruments censored. Preliminary reports are not full quality-controlled "
             "time series. Coordinate precision, one- versus two-minute duration, unresolved exposure, "
             "and sensor outages confound model errors. Fixed missing RMW, symmetric radial decay, "
             "no terrain and no explicit inland boundary-layer decay remain structural limitations. "
             "Wind verification cannot validate assumed damage curves or actual insurance recoveries.", "",
             "The next step is a locked multi-event test set of quality-controlled station time series "
             "with instrument uptime, site exposure and best-track provenance, followed by size/asymmetry "
             "diagnostics. Obtain confirmation that those data were withheld from any model fitting and "
             "document possible use by NHC. Fit any richer wind model on separate events and evaluate "
             "it on the locked storms before replacing the existing loss model.", "", "## Reproduce and audit", "",
             "```bash", "python -m hurricane_risk.validation", "python -m unittest discover -s tests -v", "```", "",
             "Inputs, source URLs, QC decisions, observation and track hashes, configuration, software "
             "versions and code hashes are retained in `manifest.json`. Pairwise residuals, exclusions, "
             "leave-one-storm-out predictions, bootstrap replicates, metric tables and loss sensitivities "
             "are adjacent CSVs. `validation_diagnostics.png` visualizes nominal errors, held-out "
             "correction errors and conditional AAL sensitivity. `observed_footprints.png` overlays "
             "station peaks on modeled geographic footprints using one wind color scale. White lines "
             "are best tracks; scalloping near the eye reflects the configured 30-minute sampling.", "",
             "![Wind validation diagnostics](validation_diagnostics.png)", "",
             "![Modeled footprints and observed station peaks](observed_footprints.png)", "", "Sources:", ""]
    for src in sources["sources"].values():
        text.append(f"- [{src['product']}]({src['url']}) — {src['section']}.")
    text += [f"- [NOAA sustained-wind duration guidance]({sources['duration_reference']}).", ""]
    (out / "wind_validation_report.md").write_text("\n".join(text))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracks", type=Path, default=Path("data/hurdat2-1851-2024-040425.txt"))
    parser.add_argument("--observations", type=Path, default=Path("data/validation/station_peaks.csv"))
    parser.add_argument("--sources", type=Path, default=Path("data/validation/sources.json"))
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--portfolio", type=Path)
    parser.add_argument("--vulnerability", type=Path)
    parser.add_argument("--out", type=Path, default=Path("reports/wind_validation"))
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    validate_config(cfg)
    vulnerability = load_vulnerability(args.vulnerability)
    portfolio = load_portfolio(args.portfolio, vulnerability) if args.portfolio else None
    sources = json.loads(args.sources.read_text())
    obs = load_observations(args.observations, sources)
    tracks = read_hurdat(args.tracks)
    if tracks.season.min() > cfg["start_year"] or tracks.season.max() < cfg["end_year"]:
        raise ValueError("Track catalog does not span configured loss-analysis years")
    pairs = footprint_predictions(obs, tracks, sources, cfg)
    pairs = uncertainty_bands(pairs, cfg["seed"] + 10, cfg["land_exposure_factor"])
    primary = pairs[pairs.primary]
    loeo = leave_one_storm_out(primary)
    boot = bootstrap_metrics(primary, 2000, cfg["seed"] + 11)
    rows = []
    for sample, group in [("pooled", primary), *list(primary.groupby("storm_id"))]:
        for comparison, column in [("nominal", "modeled_ms"), ("open_exposure", "open_exposure_ms")]:
            rows.append({"sample": sample, "comparison": comparison, **scores(group.observed_ms, group[column])})
    rows.append({"sample": "pooled", "comparison": "observations_plus_5pct_duration_sensitivity",
                 **scores(primary.observed_ms*1.05, primary.modeled_ms)})
    rows.append({"sample": "pooled", "comparison": "leave_one_storm_out_correction",
                 **scores(loeo.observed_ms, loeo.loeo_corrected_ms)})
    without_ian = primary[primary.storm_id != "AL092022"]
    if len(without_ian):
        rows.append({"sample": "pooled_without_Ian", "comparison": "nominal",
                     **scores(without_ian.observed_ms, without_ian.modeled_ms)})
    metric_table = pd.DataFrame(rows)
    factor = correction_factor(primary)
    factors = {"nominal": 1., "wind_minus_10pct": .9, "wind_plus_10pct": 1.1,
               "empirical_p05": float(boot.wind_correction_factor.quantile(.05)),
               "empirical_fit": factor, "empirical_p95": float(boot.wind_correction_factor.quantile(.95))}
    destination = args.out
    with output_directory(destination) as out:
        pairs.to_csv(out / "station_pairs.csv", index=False)
        loeo.to_csv(out / "held_out_predictions.csv", index=False)
        boot.to_csv(out / "storm_bootstrap.csv", index=False)
        metric_table.to_csv(out / "performance.csv", index=False)
        print(f"Matched {len(pairs)} station/event records; {len(primary)} eligible primary comparisons", flush=True)
        losses = loss_implications(tracks, cfg, factors, out, portfolio, vulnerability)
        diagnostic_plot(pairs, loeo, losses, out)
        footprint_plot(pairs, tracks, sources, cfg, out)
        write_report(pairs, metric_table, boot, loeo, losses, sources, cfg, out, factor)
        manifest = {"purpose": "external station-peak evaluation; not strictly withheld validation",
                    "inputs": {str(p): sha256(p) for p in [p for p in [args.tracks, args.observations, args.sources, args.config, args.portfolio, args.vulnerability] if p]},
                    "config": cfg, "sources": sources, "bootstrap_replicates": 2000,
                    "bootstrap_seed": cfg["seed"]+11, "ensemble_seed": cfg["seed"]+10,
                    "versions": {"numpy": np.__version__, "pandas": pd.__version__, "matplotlib": matplotlib.__version__},
                    "code_sha256": {str(p): sha256(p) for p in Path(__file__).parent.glob("*.py")},
                    "eligible_pairs": len(primary), "eligible_storms": int(primary.storm_id.nunique()),
                    "custom_exposure": bool(args.portfolio), "vulnerability_metadata": vulnerability["metadata"],
                    "model_changed": bool(args.vulnerability), "outputs_sha256": output_hashes(out)}
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
        print(metric_table.to_string(index=False))

    print(f"Report: {destination / 'wind_validation_report.md'}")


if __name__ == "__main__":
    main()
