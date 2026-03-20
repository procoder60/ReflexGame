from __future__ import annotations

import argparse
from pathlib import Path
import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


BANDS = ["Delta", "Theta", "Alpha", "Beta", "Gamma"]
ELECTRODES = ["TP9", "AF7", "AF8", "TP10"]
ELECTRODE_COLORS = {"TP9": "tab:blue", "AF7": "tab:green", "AF8": "tab:orange", "TP10": "tab:red"}


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _build_column_lookup(columns: list[str]) -> dict[str, str]:
    return {_normalize(c): c for c in columns}


def _find_first_column(columns: list[str], candidates: list[str]) -> str | None:
    lookup = _build_column_lookup(columns)
    for candidate in candidates:
        key = _normalize(candidate)
        if key in lookup:
            return lookup[key]
    for candidate in candidates:
        key = _normalize(candidate)
        for norm, original in lookup.items():
            if key in norm:
                return original
    return None


def _find_axis_columns(columns: list[str], group_tokens: list[str]) -> tuple[str, str, str] | None:
    norm_to_original = _build_column_lookup(columns)
    for token in group_tokens:
        t = _normalize(token)
        x = None
        y = None
        z = None
        for norm, original in norm_to_original.items():
            if t in norm and (norm.endswith("x") or "x" + t in norm or t + "x" in norm):
                x = original
            if t in norm and (norm.endswith("y") or "y" + t in norm or t + "y" in norm):
                y = original
            if t in norm and (norm.endswith("z") or "z" + t in norm or t + "z" in norm):
                z = original
        if x and y and z:
            return x, y, z
    return None


def _time_seconds(df: pd.DataFrame) -> np.ndarray:
    time_col = _find_first_column(
        list(df.columns),
        ["TimeStamp", "Timestamp", "Time", "Seconds", "Second", "UnixTime", "DateTime"],
    )

    if time_col is None:
        return np.arange(len(df), dtype=float)

    s = df[time_col]
    numeric = pd.to_numeric(s, errors="coerce")
    if numeric.notna().sum() > 0:
        arr = numeric.to_numpy(dtype=float)
        valid = np.isfinite(arr)
        if valid.sum() > 1:
            first_valid = arr[valid][0]
            if first_valid > 1e12:
                arr = arr / 1000.0
            return arr - np.nanmin(arr)

    dt = pd.to_datetime(s, errors="coerce")
    if dt.notna().sum() > 1:
        base = dt.dropna().iloc[0]
        delta = (dt - base).dt.total_seconds().to_numpy(dtype=float)
        return delta

    return np.arange(len(df), dtype=float)


def _extract_mindmonitor_band_series(df: pd.DataFrame, electrodes: list[str] | None = None) -> dict[str, np.ndarray]:
    columns = list(df.columns)
    band_series: dict[str, np.ndarray] = {}
    
    if electrodes is None:
        electrodes = ELECTRODES

    for band in BANDS:
        band_columns = []
        for ch_name in electrodes:
            col = _find_first_column(columns, [f"{band}_{ch_name}"])
            if col is not None:
                band_columns.append(col)

        if band_columns:
            numeric = pd.DataFrame({c: pd.to_numeric(df[c], errors="coerce") for c in band_columns})
            # Forward-fill and backward-fill missing values to ensure no gaps
            numeric = numeric.ffill().bfill()
            band_series[band] = numeric.mean(axis=1, skipna=True).to_numpy(dtype=float)

    return band_series


def _extract_heart_rate(df: pd.DataFrame) -> tuple[np.ndarray, str | None]:
    col = _find_first_column(list(df.columns), ["HeartRate", "Heart Rate", "HR", "BPM", "Pulse"])
    if col is None:
        return np.full(len(df), np.nan, dtype=float), None
    series = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
    return series, col


def _extract_motion(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, str | None, str | None]:
    columns = list(df.columns)

    acc_xyz = _find_axis_columns(columns, ["Accelerometer", "Accel", "Acc"])
    gyro_xyz = _find_axis_columns(columns, ["Gyro", "Gyroscope"])

    acc_max = np.full(len(df), np.nan, dtype=float)
    gyro_max = np.full(len(df), np.nan, dtype=float)
    acc_label = None
    gyro_label = None

    if acc_xyz is not None:
        x, y, z = acc_xyz
        ax = pd.to_numeric(df[x], errors="coerce").to_numpy(dtype=float)
        ay = pd.to_numeric(df[y], errors="coerce").to_numpy(dtype=float)
        az = pd.to_numeric(df[z], errors="coerce").to_numpy(dtype=float)
        # Heavy smoothing and derivative per axis, then average
        ax_smooth = _smooth_signal(ax, window=50)
        ay_smooth = _smooth_signal(ay, window=50)
        az_smooth = _smooth_signal(az, window=50)
        ax_deriv = np.abs(np.gradient(ax_smooth))
        ay_deriv = np.abs(np.gradient(ay_smooth))
        az_deriv = np.abs(np.gradient(az_smooth))
        acc_max = np.nanmean([ax_deriv, ay_deriv, az_deriv], axis=0) * 100
        acc_label = f"Accel motion score (avg derivative)"

    if gyro_xyz is not None:
        x, y, z = gyro_xyz
        gx = pd.to_numeric(df[x], errors="coerce").to_numpy(dtype=float)
        gy = pd.to_numeric(df[y], errors="coerce").to_numpy(dtype=float)
        gz = pd.to_numeric(df[z], errors="coerce").to_numpy(dtype=float)
        # Heavy smoothing and derivative per axis, then average
        gx_smooth = _smooth_signal(gx, window=50)
        gy_smooth = _smooth_signal(gy, window=50)
        gz_smooth = _smooth_signal(gz, window=50)
        gx_deriv = np.abs(np.gradient(gx_smooth))
        gy_deriv = np.abs(np.gradient(gy_smooth))
        gz_deriv = np.abs(np.gradient(gz_smooth))
        gyro_max = np.nanmean([gx_deriv, gy_deriv, gz_deriv], axis=0)
        gyro_label = f"Gyro motion score (avg derivative)"

    return acc_max, gyro_max, acc_label, gyro_label


def _extract_quality(df: pd.DataFrame) -> dict[str, np.ndarray]:
    columns = list(df.columns)
    quality_data = {}
    
    for ch_name in ELECTRODES:
        col = _find_first_column(columns, [f"HSI_{ch_name}"])
        if col is not None:
            quality_data[ch_name] = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
    
    return quality_data


def _compute_robust_ylim(values: list, percentile_low: float = 5.0, percentile_high: float = 95.0, padding_fraction: float = 0.15) -> tuple[float, float] | None:
    """Compute robust Y-axis limits using percentiles to avoid outlier distortion.
    
    Args:
        values: List of values (can contain NaN)
        percentile_low: Lower percentile (default 5th)
        percentile_high: Upper percentile (default 95th)
        padding_fraction: Fraction of range to add as padding (default 0.15 = 15%)
    
    Returns:
        Tuple of (ymin, ymax) or None if no valid values
    """
    if not values:
        return None
    
    valid_values = [v for v in values if np.isfinite(v)]
    if not valid_values:
        return None
    
    p_low = np.percentile(valid_values, percentile_low)
    p_high = np.percentile(valid_values, percentile_high)
    range_val = p_high - p_low
    padding = padding_fraction * range_val if range_val > 0 else padding_fraction
    
    return (p_low - padding, p_high + padding)


def _smooth_signal(signal: np.ndarray, window: int = 5) -> np.ndarray:
    """Smooth signal using a moving average filter."""
    if len(signal) < window:
        return signal
    
    # First, forward-fill and backward-fill any NaN values to avoid gaps
    signal_filled = signal.copy()
    mask = np.isnan(signal_filled)
    if mask.any():
        # Forward fill
        indices = np.arange(len(signal_filled))
        valid_indices = indices[~mask]
        if len(valid_indices) > 0:
            signal_filled[mask] = np.interp(indices[mask], valid_indices, signal_filled[valid_indices], left=np.nan, right=np.nan)
        # Backward fill remaining NaNs at the start
        first_valid = np.where(~np.isnan(signal_filled))[0]
        if len(first_valid) > 0:
            signal_filled[:first_valid[0]] = signal_filled[first_valid[0]]
        # Forward fill remaining NaNs at the end
        last_valid = np.where(~np.isnan(signal_filled))[0]
        if len(last_valid) > 0:
            signal_filled[last_valid[-1]+1:] = signal_filled[last_valid[-1]]
    
    kernel = np.ones(window) / window
    smoothed = np.convolve(signal_filled, kernel, mode='same')
    return smoothed


def _compute_concentration_relaxation(band_series: dict[str, np.ndarray]) -> dict[str, dict[str, np.ndarray]]:
    """Compute multiple concentration and relaxation scores from brain wave ratios.
    
    Returns dict with 'concentration' and 'relaxation' keys, each containing multiple formulations.
    """
    beta = band_series.get("Beta")
    theta = band_series.get("Theta")
    alpha = band_series.get("Alpha")
    gamma = band_series.get("Gamma")
    
    n = len(beta) if beta is not None else 0
    
    concentration_formulas = {}
    relaxation_formulas = {}
    
    smoothing_window = 50  # Adjust as needed for more or less smoothing

    # Concentration formulas
    if beta is not None and theta is not None and alpha is not None:
        # Formula 1: Beta / (Theta + Alpha)
        denominator = theta + alpha
        valid = (denominator > 0) & np.isfinite(beta) & np.isfinite(theta) & np.isfinite(alpha)
        conc1 = np.full(n, np.nan, dtype=float)
        conc1[valid] = beta[valid] / denominator[valid]
        concentration_formulas['Beta/(Theta+Alpha)'] = _smooth_signal(conc1, window=smoothing_window)
    
    if beta is not None and theta is not None:
        # Formula 2: Beta / Theta
        valid = (theta > 0) & np.isfinite(beta) & np.isfinite(theta)
        conc2 = np.full(n, np.nan, dtype=float)
        conc2[valid] = beta[valid] / theta[valid]
        concentration_formulas['Beta/Theta'] = _smooth_signal(conc2, window=smoothing_window)
    
    if beta is not None and gamma is not None and alpha is not None:
        # Formula 3: (Beta + Gamma) / Alpha
        valid = (alpha > 0) & np.isfinite(beta) & np.isfinite(gamma) & np.isfinite(alpha)
        conc3 = np.full(n, np.nan, dtype=float)
        conc3[valid] = (beta[valid] + gamma[valid]) / alpha[valid]
        concentration_formulas['(Beta+Gamma)/Alpha'] = _smooth_signal(conc3, window=smoothing_window)
    
    # Relaxation formulas
    if alpha is not None and beta is not None and gamma is not None:
        # Formula 1: Alpha / (Beta + Gamma)
        denominator = beta + gamma
        valid = (denominator > 0) & np.isfinite(alpha) & np.isfinite(beta) & np.isfinite(gamma)
        relax1 = np.full(n, np.nan, dtype=float)
        relax1[valid] = alpha[valid] / denominator[valid]
        relaxation_formulas['Alpha/(Beta+Gamma)'] = _smooth_signal(relax1, window=smoothing_window)
    
    if alpha is not None and beta is not None:
        # Formula 2: Alpha / Beta
        valid = (beta > 0) & np.isfinite(alpha) & np.isfinite(beta)
        relax2 = np.full(n, np.nan, dtype=float)
        relax2[valid] = alpha[valid] / beta[valid]
        relaxation_formulas['Alpha/Beta'] = _smooth_signal(relax2, window=smoothing_window)
    
    if theta is not None and beta is not None:
        # Formula 3: Theta / Beta
        valid = (beta > 0) & np.isfinite(theta) & np.isfinite(beta)
        relax3 = np.full(n, np.nan, dtype=float)
        relax3[valid] = theta[valid] / beta[valid]
        relaxation_formulas['Theta/Beta'] = _smooth_signal(relax3, window=smoothing_window)
    
    if alpha is not None and theta is not None and beta is not None:
        # Formula 4: (Alpha + Theta) / Beta
        valid = (beta > 0) & np.isfinite(alpha) & np.isfinite(theta) & np.isfinite(beta)
        relax4 = np.full(n, np.nan, dtype=float)
        relax4[valid] = (alpha[valid] + theta[valid]) / beta[valid]
        relaxation_formulas['(Alpha+Theta)/Beta'] = _smooth_signal(relax4, window=smoothing_window)
    
    return {'concentration': concentration_formulas, 'relaxation': relaxation_formulas}


def plot_mind_monitor(csv_path: Path, output_path: Path | None = None, show: bool = True, electrodes: list[str] | None = None) -> Path:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    df = pd.read_csv(csv_path)
    if df.empty:
        raise ValueError("CSV file is empty.")

    time_s = _time_seconds(df)
    mm_band_series = _extract_mindmonitor_band_series(df, electrodes=electrodes)
    scores = _compute_concentration_relaxation(mm_band_series)
    concentration_formulas = scores['concentration']
    relaxation_formulas = scores['relaxation']
    hr, hr_col = _extract_heart_rate(df)
    acc_max, gyro_max, acc_label, gyro_label = _extract_motion(df)
    quality_data = _extract_quality(df)

    fig, axes = plt.subplots(6, 1, figsize=(13, 16), sharex=False)

    color_map = {
        "Delta": "tab:blue",
        "Theta": "tab:orange",
        "Alpha": "tab:green",
        "Beta": "tab:red",
        "Gamma": "tab:purple",
    }

    # 1. Brain Waves
    for band in BANDS:
        mm_values = mm_band_series.get(band)
        if mm_values is not None and np.isfinite(mm_values).any():
            axes[0].plot(
                time_s,
                mm_values,
                label=band,
                linewidth=1.5,
                color=color_map.get(band),
            )
    # Add electrode info to title
    electrode_info = ""
    if electrodes and electrodes != ELECTRODES:
        electrode_info = f" (electrodes: {', '.join(electrodes)})"
    axes[0].set_title(f"Brain Waves Over Time (Mind Monitor - averaged across electrodes){electrode_info}")
    axes[0].set_ylabel("Power")
    axes[0].legend(loc="upper right", ncol=5)
    axes[0].grid(alpha=0.3)

    # 2. Concentration Scores (multiple formulations)
    if concentration_formulas:
        colors = ['tab:purple', 'tab:pink', 'darkviolet']
        all_valid = []
        for idx, (name, values) in enumerate(concentration_formulas.items()):
            if np.isfinite(values).any():
                axes[1].plot(time_s, values, label=name, linewidth=1.5, color=colors[idx % len(colors)], alpha=0.85)
                all_valid.extend(values[np.isfinite(values)])
        
        if all_valid:
            # Set robust Y-axis limits using percentiles across all formulas
            ylim = _compute_robust_ylim(all_valid)
            if ylim:
                axes[1].set_ylim(ylim)
            axes[1].legend(loc="upper right", fontsize=9)
        axes[1].set_ylabel("Concentration")
    else:
        axes[1].text(0.02, 0.5, "Cannot compute concentration (missing bands)", transform=axes[1].transAxes, va="center")
        axes[1].set_ylabel("Concentration")
    axes[1].set_title("Concentration Scores (smoothed, multiple formulations)")
    axes[1].grid(alpha=0.3)

    # 3. Relaxation Scores (multiple formulations)
    if relaxation_formulas:
        colors = ['tab:cyan', 'deepskyblue', 'teal', 'lightseagreen']
        all_valid = []
        for idx, (name, values) in enumerate(relaxation_formulas.items()):
            if np.isfinite(values).any():
                axes[2].plot(time_s, values, label=name, linewidth=1.5, color=colors[idx % len(colors)], alpha=0.85)
                all_valid.extend(values[np.isfinite(values)])
        
        if all_valid:
            # Set robust Y-axis limits using percentiles across all formulas
            ylim = _compute_robust_ylim(all_valid, padding_fraction=0.3)
            if ylim:
                axes[2].set_ylim(ylim)
            axes[2].legend(loc="upper right", fontsize=9)
        axes[2].set_ylabel("Relaxation")
    else:
        axes[2].text(0.02, 0.5, "Cannot compute relaxation (missing bands)", transform=axes[2].transAxes, va="center")
        axes[2].set_ylabel("Relaxation")
    axes[2].set_title("Relaxation Scores (smoothed, multiple formulations)")
    axes[2].grid(alpha=0.3)

    # 4. Motion
    plotted_motion = False
    motion_values = []
    if np.isfinite(acc_max).any():
        axes[3].plot(time_s, acc_max, label=acc_label or "Accel max", linewidth=1.2, color="tab:blue")
        motion_values.extend(acc_max[np.isfinite(acc_max)])
        plotted_motion = True
    if np.isfinite(gyro_max).any():
        axes[3].plot(time_s, gyro_max, label=gyro_label or "Gyro max", linewidth=1.2, color="tab:orange")
        motion_values.extend(gyro_max[np.isfinite(gyro_max)])
        plotted_motion = True
    if plotted_motion:
        axes[3].legend(loc="upper right")
        # Set robust Y-axis limits using percentiles
        ylim = _compute_robust_ylim(motion_values)
        if ylim:
            axes[3].set_ylim(ylim)
    else:
        axes[3].text(0.02, 0.5, "No motion data found", transform=axes[3].transAxes, va="center")
    axes[3].set_title("Motion Score Over Time (derivative of heavily smoothed signal)")
    axes[3].set_ylabel("Motion score (rate of change)")
    axes[3].grid(alpha=0.3)

    # 5. Heart Rate
    if np.isfinite(hr).any():
        axes[4].plot(time_s, hr, color="crimson", linewidth=1.2)
        label = "Heart rate (bpm)" if hr_col is None else f"Heart rate (from {hr_col})"
        axes[4].set_ylabel(label)
    else:
        axes[4].text(0.02, 0.5, "No heart-rate data found", transform=axes[4].transAxes, va="center")
        axes[4].set_ylabel("Heart rate")
    axes[4].set_title("Heart Rate Over Time")
    axes[4].grid(alpha=0.3)

    # 6. Quality (HSI)
    if quality_data:
        for ch_name, values in quality_data.items():
            if np.isfinite(values).any():
                axes[5].plot(time_s, values, label=f"HSI_{ch_name}", linewidth=1.0, color=ELECTRODE_COLORS.get(ch_name))
        axes[5].legend(loc="upper right", ncol=4)
    else:
        axes[5].text(0.02, 0.5, "No quality (HSI) data found", transform=axes[5].transAxes, va="center")
    axes[5].set_title("Signal Quality Over Time (HSI values)")
    axes[5].set_ylabel("Quality")
    # Set x-axis label only for the bottom subplot
    for i, ax in enumerate(axes):
        if i == len(axes) - 1:
            ax.set_xlabel("Time (seconds)")
        else:
            ax.set_xlabel("")
    axes[5].grid(alpha=0.3)

    # Configure time axis ticks for all subplots: major ticks every 60s, minor ticks every 10s
    from matplotlib.ticker import MultipleLocator, FormatStrFormatter
    for ax in axes:
        ax.xaxis.set_major_locator(MultipleLocator(60))
        ax.xaxis.set_minor_locator(MultipleLocator(10))
        ax.xaxis.set_major_formatter(FormatStrFormatter('%.0f'))  # Show numbers as integers
        ax.grid(which='major', alpha=0.3)
        ax.grid(which='minor', alpha=0.1, linestyle=':')
        # Ensure x-tick labels are visible for all subplots
        ax.tick_params(axis='x', which='both', labelbottom=True)
        # Add x value labels at each major tick
        for label in ax.get_xticklabels():
            label.set_visible(True)

    fig.tight_layout()

    if output_path is None:
        output_path = csv_path.with_name(csv_path.stem + "_plots.png")
    fig.savefig(output_path, dpi=150)

    if show:
        plt.show()
    else:
        plt.close(fig)

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot Mind Monitor data: brain waves, motion, heart rate, and quality.")
    parser.add_argument(
        "csv",
        nargs="*",
        default=["data/mindMonitor_2026-03-01--16-04-14_6815096722775041305.csv"],
        help="Path(s) to Mind Monitor CSV export(s). Can specify multiple files.",
    )
    parser.add_argument("--output-dir", default=None, help="Optional output directory for PNG files (default: same directory as CSV).")
    parser.add_argument("--no-show", action="store_true", help="Do not open a plot window.")
    parser.add_argument(
        "--electrodes",
        nargs="+",
        default=None,
        choices=ELECTRODES,
        help="Electrodes to use for brain wave analysis (default: all [TP9, AF7, AF8, TP10]).",
    )
    args = parser.parse_args()

    # Ensure csv is a list
    csv_files = args.csv if isinstance(args.csv, list) else [args.csv]
    
    # Filter to only CSV files
    csv_files = [f for f in csv_files if str(f).lower().endswith('.csv')]
    
    if not csv_files:
        print("Error: No CSV files specified.")
        return
    
    output_dir = Path(args.output_dir) if args.output_dir else None
    
    for csv_file in csv_files:
        csv_path = Path(csv_file)
        
        # If electrodes not specified, generate plot with all electrodes and then individual electrode plots
        electrode_configs = None
        if args.electrodes is None:
            electrode_configs = [None] + [[e] for e in ELECTRODES]  # None for all, then individual
        else:
            electrode_configs = [args.electrodes]
        
        for electrodes in electrode_configs:
            # Determine output path with electrode info
            if output_dir:
                if electrodes is None:
                    output_path = output_dir / (csv_path.stem + "_all-electrodes_plots.png")
                else:
                    electrode_str = "-".join(electrodes)
                    output_path = output_dir / (csv_path.stem + f"_{electrode_str}_plots.png")
            else:
                if electrodes is None:
                    output_path = csv_path.with_name(csv_path.stem + "_all-electrodes_plots.png")
                else:
                    electrode_str = "-".join(electrodes)
                    output_path = csv_path.with_name(csv_path.stem + f"_{electrode_str}_plots.png")
            
            # Format electrode info for display
            if electrodes is None:
                electrode_info = "all electrodes"
            else:
                electrode_info = ", ".join(electrodes)
            
            print(f"Processing: {csv_path} ({electrode_info})")
            try:
                saved = plot_mind_monitor(csv_path=csv_path, output_path=output_path, show=not args.no_show, electrodes=electrodes)
                print(f"  ✓ Saved plot to: {saved}")
            except Exception as e:
                print(f"  ✗ Error processing {csv_path}: {e}")


if __name__ == "__main__":
    main()
