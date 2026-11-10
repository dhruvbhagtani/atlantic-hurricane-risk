"""Track parsing, assumed wind/vulnerability models, and annual loss statistics."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

KNOT_TO_MS = 0.514444
NOAA_URL = "https://www.nhc.noaa.gov/data/hurdat/hurdat2-1851-2024-040425.txt"
WIND_NODES = np.array([0, 20, 30, 40, 50, 60, 70, 85, 100], dtype=float)
# Explicit assumptions for one-minute sustained 10-m wind in m/s, not FEMA curves.
DAMAGE_NODES = {
    "wood": np.array([0, 0, .015, .08, .25, .50, .75, .95, 1]),
    "masonry": np.array([0, 0, .005, .04, .15, .35, .60, .85, 1]),
    "mitigated": np.array([0, 0, .002, .015, .06, .18, .38, .65, .9]),
}


def coordinate(value: str) -> float:
    if not re.fullmatch(r"\d+(?:\.\d+)?[NSEW]", value):
        raise ValueError(f"Invalid HURDAT2 coordinate: {value}")
    return float(value[:-1]) * (-1 if value[-1] in "SW" else 1)


def read_hurdat(path: Path) -> pd.DataFrame:
    """Read variable-width comma-delimited HURDAT2; reject incomplete storms."""
    rows = []
    lines = iter(path.read_text().splitlines())
    for line in lines:
        if not line.strip():
            continue
        header = [s.strip() for s in line.split(",")]
        if not re.fullmatch(r"AL\d{6}", header[0]):
            raise ValueError(f"Expected Atlantic HURDAT2 header: {line[:80]}")
        sid, name, count = header[:3]
        for _ in range(int(count)):
            try:
                fields = [s.strip() for s in next(lines).split(",")]
            except StopIteration as exc:
                raise ValueError(f"Truncated storm {sid}") from exc
            if len(fields) < 8:
                raise ValueError(f"Malformed record for {sid}")
            timestamp = pd.to_datetime(fields[0] + fields[1], format="%Y%m%d%H%M")
            lat, lon, wind = coordinate(fields[4]), coordinate(fields[5]), float(fields[6])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180 and (wind in (-99, -999) or 0 <= wind <= 250)):
                raise ValueError(f"Invalid coordinates/wind in {sid}")
            if wind in (-99, -999):
                wind = np.nan
            rmw = float(fields[20]) if len(fields) > 20 and fields[20] else -999
            rows.append((sid, name, int(sid[-4:]), timestamp, fields[3], lat, lon,
                         wind * KNOT_TO_MS, rmw * 1.852 if rmw > 0 else np.nan))
    if not rows:
        raise ValueError("No HURDAT2 records")
    df = pd.DataFrame(rows, columns=["storm_id", "name", "season", "time", "status",
                                    "lat", "lon", "vmax_ms", "rmw_km"])
    if df.duplicated(["storm_id", "time"]).any():
        raise ValueError("Duplicate storm timestamps")
    return df.sort_values(["storm_id", "time"]).reset_index(drop=True)


def synthetic_portfolio(n: int, seed: int) -> pd.DataFrame:
    """Synthetic addresses around Florida cities; no real insured records."""
    rng = np.random.default_rng(seed)
    cities = [("Miami", 25.76, -80.20), ("Tampa", 27.95, -82.46),
              ("Orlando", 28.54, -81.38), ("Jacksonville", 30.33, -81.66),
              ("Pensacola", 30.42, -87.22), ("Fort_Myers", 26.64, -81.87)]
    pick = rng.integers(0, len(cities), n)
    values = np.round(np.clip(rng.lognormal(np.log(400_000), .45, n), 100_000, 2_000_000), -2)
    return pd.DataFrame({
        "property_id": [f"FL{i:05d}" for i in range(n)],
        "city": [cities[i][0] for i in pick],
        "lat": [cities[i][1] for i in pick] + rng.uniform(-.025, .025, n),
        "lon": [cities[i][2] for i in pick] + rng.uniform(-.025, .025, n),
        "replacement_value_usd": values,
        "construction": rng.choice(list(DAMAGE_NODES), n, p=[.4, .4, .2]),
        "deductible_fraction": .02,
        "limit_fraction": 1.0,
    })


def interpolate_track(track: pd.DataFrame, minutes: int, fallback_rmw: float, evaluation_times=None):
    if track.empty or not np.isfinite(minutes) or minutes <= 0 or fallback_rmw <= 0:
        raise ValueError("Need a nonempty track and positive timestep/RMW")
    t = track.time.astype("int64").to_numpy() / 1e9
    if (np.diff(t) <= 0).any() or not np.isfinite(track.vmax_ms).all():
        raise ValueError("Track times must strictly increase and winds must be finite")
    if len(t) > 1 and np.max(np.diff(t)) > 12 * 3600:
        raise ValueError(f"Track gap >12 hours: {track.storm_id.iloc[0]}")
    # Retain all original fixes, including special landfall observations.
    if evaluation_times is None:
        target = np.unique(np.r_[np.arange(t[0], t[-1], minutes * 60), t])
    else:
        target = pd.to_datetime(evaluation_times, utc=True).astype('int64').to_numpy() / 1e9
        if not np.isfinite(target).all() or (target < t[0]).any() or (target > t[-1]).any():
            raise ValueError('Evaluation times must lie within the track window')
    rmw = track.rmw_km.fillna(fallback_rmw).to_numpy()
    lon = np.rad2deg(np.unwrap(np.deg2rad(track.lon.to_numpy())))
    return tuple(np.interp(target, t, x) for x in
                 [track.lat.to_numpy(), lon, track.vmax_ms.to_numpy(), rmw])


def distance_km(lat1, lon1, lat2, lon2):
    a, b = np.deg2rad(lat1), np.deg2rad(lat2)
    h = np.sin((a-b)/2)**2 + np.cos(a)*np.cos(b)*np.sin(np.deg2rad(lon1-lon2)/2)**2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def rankine_wind(distance, vmax, rmw, alpha=.6):
    """V=Vmax*r/R inside R; V=Vmax*(R/r)^alpha outside R."""
    ratio = np.asarray(distance) / rmw
    return vmax * np.where(ratio <= 1, ratio, np.maximum(ratio, 1)**(-alpha))


def interpolation_times(track, minutes, evaluation_times=None):
    t = track.time.astype('int64').to_numpy()/1e9
    if evaluation_times is not None:
        return pd.to_datetime(evaluation_times, utc=True).astype('int64').to_numpy()/1e9
    return np.unique(np.r_[np.arange(t[0], t[-1], minutes*60), t])


def translation_velocity(track, targets):
    """Differentiate original fixes, then interpolate motion components in m/s."""
    t = track.time.astype('int64').to_numpy()/1e9
    if len(t) == 1:
        return np.zeros(len(targets)), np.zeros(len(targets))
    lat = np.deg2rad(track.lat.to_numpy())
    lon = np.unwrap(np.deg2rad(track.lon.to_numpy()))
    north = np.gradient(lat, t)*6371008.8
    east = np.gradient(lon, t)*6371008.8*np.cos(lat)
    return np.interp(targets, t, east), np.interp(targets, t, north)


def surface_wind(distance, vmax, rmw, center_lat, center_lon, site_lat, site_lon,
                 cfg, motion_east=0., motion_north=0., inland_distance_km=None):
    """Shared wind kernel; optional, explicitly assumed structural sensitivities."""
    wind = rankine_wind(distance, vmax, rmw, cfg['rankine_alpha'])*cfg['land_exposure_factor']
    fraction = cfg.get('translation_fraction', 0.)
    if fraction:
        lat0, lat1 = np.deg2rad(center_lat), np.deg2rad(site_lat)
        delta = np.deg2rad(np.asarray(site_lon)-np.asarray(center_lon))
        bearing = np.arctan2(np.sin(delta)*np.cos(lat1),
                            np.cos(lat0)*np.sin(lat1)-np.sin(lat0)*np.cos(lat1)*np.cos(delta))
        speed = np.hypot(motion_east, motion_north)
        # NH counterclockwise tangential wind; reverse rotation in the SH.
        sign = np.where(np.asarray(center_lat) >= 0, 1., -1.)
        projection = sign*(-np.cos(bearing)*motion_east + np.sin(bearing)*motion_north)
        cosine = np.divide(projection, speed, out=np.zeros_like(projection), where=speed > 0)
        beta = np.minimum(cfg.get('asymmetry_cap', .25), fraction*speed/np.maximum(vmax, 1e-12))
        # Preserve best-track Vmax on the favored side, avoiding a second
        # addition of translation speed to an already earth-relative maximum.
        wind = wind*(1+beta*cosine)/(1+beta)
    length = cfg.get('inland_decay_km', 0.)
    if length:
        if inland_distance_km is None:
            raise ValueError('Local inland attenuation requires coastline distances')
        wind = wind*np.exp(-np.maximum(inland_distance_km, 0)/length)
    return wind


def hazard_catalog(tracks, portfolio, cfg):
    """Event/property maxima at three assumed RMW multipliers; no radius cutoff."""
    events, fields = [], []
    inland = None
    if cfg.get('inland_decay_km', 0.):
        from .geography import coast_distances
        inland, _ = coast_distances(portfolio.lat, portfolio.lon, cfg['coastline_path'])
    for sid, tr in tracks.groupby("storm_id", sort=True):
        lat, lon, vmax, rmw = interpolate_track(tr, cfg["interpolation_minutes"], cfg["rmw_km"])
        u, v = (translation_velocity(tr, interpolation_times(tr, cfg['interpolation_minutes']))
                if cfg.get('translation_fraction', 0.) else (np.zeros(len(lat)), np.zeros(len(lat))))
        maxima = np.zeros((3, len(portfolio)))
        for start in range(0, len(lat), 256):
            sl = slice(start, start + 256)
            r = distance_km(lat[sl, None], lon[sl, None],
                            portfolio.lat.to_numpy()[None, :], portfolio.lon.to_numpy()[None, :])
            for j, scale in enumerate([.8, 1., 1.2]):
                wind = surface_wind(r, vmax[sl, None], rmw[sl, None]*scale,
                                    lat[sl, None], lon[sl, None], portfolio.lat.to_numpy()[None, :],
                                    portfolio.lon.to_numpy()[None, :], cfg, u[sl, None], v[sl, None], inland)
                maxima[j] = np.maximum(maxima[j], wind.max(axis=0))
        fields.append(maxima)
        events.append((sid, tr.name.iloc[0], tr.season.iloc[0]))
    if not fields:
        raise ValueError("No storms reaching HU status in selected seasons")
    return pd.DataFrame(events, columns=["storm_id", "name", "year"]), np.stack(fields)


def property_losses(wind, portfolio, vulnerability_scale=1., vulnerability=None):
    from .inputs import default_vulnerability, validate_portfolio
    curves = default_vulnerability() if vulnerability is None else vulnerability
    validate_portfolio(portfolio, curves["damage_nodes"])
    wind = np.asarray(wind, dtype=float)
    if wind.ndim != 2 or wind.shape[1] != len(portfolio) or not np.isfinite(wind).all() or (wind < 0).any():
        raise ValueError("Wind must be a finite nonnegative event-by-property array")
    if not np.isfinite(vulnerability_scale) or vulnerability_scale < 0:
        raise ValueError("Vulnerability scale must be finite and nonnegative")
    damage = np.zeros_like(wind, dtype=float)
    for kind, nodes in curves["damage_nodes"].items():
        mask = portfolio.construction.to_numpy() == kind
        damage[:, mask] = np.interp(wind[:, mask], curves["wind_nodes_ms"], nodes)
    damage = np.clip(damage * vulnerability_scale, 0, 1)
    value = portfolio.replacement_value_usd.to_numpy()
    ground_up = damage * value
    insured = np.minimum(np.maximum(ground_up - value * portfolio.deductible_fraction.to_numpy(), 0),
                         value * portfolio.limit_fraction.to_numpy())
    return ground_up, insured


def annual_losses(event_losses, event_years, years):
    years = np.asarray(years)
    event_years = np.asarray(event_years)
    event_losses = np.asarray(event_losses, dtype=float)
    if years.ndim != 1 or not len(years) or not np.isfinite(years).all() or (years != np.floor(years)).any() or (np.diff(years) != 1).any():
        raise ValueError("Years must be consecutive increasing integers")
    if event_years.ndim != 1 or event_losses.shape != event_years.shape or not np.isin(event_years, years).all():
        raise ValueError("Event years must belong to the annual catalog and match event losses")
    if not np.isfinite(event_losses).all() or (event_losses < 0).any():
        raise ValueError("Event losses must be finite and nonnegative")
    sums, maxima = np.zeros(len(years)), np.zeros(len(years))
    index = np.asarray(event_years, dtype=int) - int(years[0])
    np.add.at(sums, index, event_losses)
    np.maximum.at(maxima, index, event_losses)
    return sums, maxima


def sample_annual_blocks(aggregate, occurrence, indices, uniforms, frequency):
    """Superpose floor(f) annual blocks plus a Bernoulli(f-floor(f)) block."""
    whole = int(np.floor(frequency))
    total = np.zeros(indices.shape[0])
    peak = np.zeros(indices.shape[0])
    for j in range(whole + 1):
        active = np.ones(len(total), dtype=bool) if j < whole else uniforms < frequency-whole
        total += aggregate[indices[:, j]] * active
        peak = np.maximum(peak, occurrence[indices[:, j]] * active)
    return total, peak


def ep_curve(annual, thresholds):
    """Strict P(L > x), including zero-loss years in denominator."""
    ordered = np.sort(annual)
    return (len(ordered) - np.searchsorted(ordered, thresholds, side="right")) / len(ordered)


def loss_metrics(aggregate, occurrence, periods):
    result = {"aal_usd": float(np.mean(aggregate))}
    for period in periods:
        for key, values in [("aep", aggregate), ("oep", occurrence)]:
            result[f"{key}_{period:g}yr_usd"] = float(np.quantile(values, 1 - 1/period, method="inverted_cdf"))
    return result
