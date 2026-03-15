"""Matplotlib ile 4-panellik uçuş özeti grafiği."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.ticker import AutoMinorLocator

# Her faz için renk
_STATE_COLORS = {
    "IDLE":          "#aaaaaa",
    "ARMED":         "#5555ff",
    "LAUNCH_DETECT": "#ff9900",
    "ASCENT":        "#00cc44",
    "APOGEE":        "#ff4444",
    "DESCENT":       "#ff8888",
    "LANDED":        "#884422",
    "ERROR":         "#ff00ff",
}


def _state_spans(df: pd.DataFrame) -> list:
    """Ardışık aynı fazları (start_s, end_s, state_name) üçlüleri olarak döner."""
    spans = []
    t_ms = df["timestamp"].values / 1000.0
    states = df["state"].values
    i = 0
    while i < len(states):
        j = i + 1
        while j < len(states) and states[j] == states[i]:
            j += 1
        spans.append((t_ms[i], t_ms[j - 1], states[i]))
        i = j
    return spans


def _shade_phases(ax, spans: list):
    """Her faz aralığını renkli arka planla işaretle."""
    for t_start, t_end, state in spans:
        color = _STATE_COLORS.get(state, "#cccccc")
        ax.axvspan(t_start, t_end, alpha=0.12, color=color, linewidth=0)


def _add_event_lines(ax, df: pd.DataFrame):
    """Faz geçiş anlarına dikey kesik çizgi + etiket ekler."""
    t_ms = df["timestamp"].values / 1000.0
    states = df["state"].values
    prev = states[0]
    for i in range(1, len(states)):
        if states[i] != prev:
            ax.axvline(t_ms[i], color="gray", linestyle="--", linewidth=0.8, alpha=0.7)
            ax.text(t_ms[i], ax.get_ylim()[1] * 0.95, states[i],
                    fontsize=6, rotation=90, va="top", ha="right", color="gray")
            prev = states[i]


def plot_flight(df: pd.DataFrame, save_path: str | Path | None = None,
                show: bool = True):
    """4-panellik uçuş grafiği çizer. save_path verilirse PNG kaydeder."""
    t = df["timestamp"].values / 1000.0  # saniyeye çevir
    altitude = df["altitude"].values
    accel_x = df["accel_x"].values
    spans = _state_spans(df)

    # Hız: irtifanın fark quotient'ı (gürültülü baro'dan türev)
    dt = t[1] - t[0] if len(t) > 1 else 0.01
    velocity = pd.Series(altitude).diff().fillna(0).values / dt

    fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)
    fig.suptitle("Roket Uçuş Simülasyonu — Özet", fontsize=13, fontweight="bold")

    # --- Panel 1: İrtifa ---
    ax = axes[0]
    _shade_phases(ax, spans)
    ax.plot(t, altitude, color="#0055cc", linewidth=1.2, label="Baro. İrtifa")
    apogee_idx = df["altitude"].idxmax()
    ax.scatter(t[apogee_idx], altitude[apogee_idx], color="red", zorder=5, s=40)
    ax.annotate(f"Apogee\n{altitude[apogee_idx]:.0f} m",
                xy=(t[apogee_idx], altitude[apogee_idx]),
                xytext=(t[apogee_idx] + 1, altitude[apogee_idx] * 0.9),
                fontsize=8, arrowprops=dict(arrowstyle="->", color="red"), color="red")
    ax.set_ylabel("İrtifa (m)")
    ax.yaxis.set_minor_locator(AutoMinorLocator())
    ax.grid(True, which="major", alpha=0.4)
    ax.legend(fontsize=8, loc="upper right")

    # --- Panel 2: Hız ---
    ax = axes[1]
    _shade_phases(ax, spans)
    ax.plot(t, velocity, color="#009944", linewidth=1.0, label="Dikey Hız")
    ax.axhline(0, color="black", linewidth=0.6, linestyle=":")
    ax.set_ylabel("Hız (m/s)")
    ax.yaxis.set_minor_locator(AutoMinorLocator())
    ax.grid(True, which="major", alpha=0.4)
    ax.legend(fontsize=8, loc="upper right")

    # --- Panel 3: İvme ---
    ax = axes[2]
    _shade_phases(ax, spans)
    ax.plot(t, accel_x, color="#cc4400", linewidth=0.8, label="İvme X (g)")
    ax.axhline(1.0, color="gray", linewidth=0.6, linestyle=":", label="1g")
    ax.set_ylabel("İvme (g)")
    ax.yaxis.set_minor_locator(AutoMinorLocator())
    ax.grid(True, which="major", alpha=0.4)
    ax.legend(fontsize=8, loc="upper right")

    # --- Panel 4: Faz Gantt ---
    ax = axes[3]
    unique_states = list(dict.fromkeys(s for _, _, s in spans))
    y_map = {s: i for i, s in enumerate(unique_states)}
    for t_start, t_end, state in spans:
        color = _STATE_COLORS.get(state, "#cccccc")
        ax.barh(y_map[state], t_end - t_start, left=t_start,
                color=color, edgecolor="white", linewidth=0.3, height=0.6)
    ax.set_yticks(list(y_map.values()))
    ax.set_yticklabels(list(y_map.keys()), fontsize=8)
    ax.set_ylabel("Faz")
    ax.set_xlabel("Zaman (s)")
    ax.grid(True, axis="x", alpha=0.4)

    # Ortak faz renk açıklaması
    patches = [mpatches.Patch(color=_STATE_COLORS.get(s, "#ccc"), label=s)
               for s in unique_states]
    fig.legend(handles=patches, loc="upper center", ncol=len(unique_states),
               fontsize=7, bbox_to_anchor=(0.5, 0.98))

    plt.tight_layout(rect=[0, 0, 1, 0.96])

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Grafik kaydedildi: {save_path}")

    if show:
        plt.show()

    plt.close(fig)


def plot_from_csv(csv_path: str | Path, save_path: str | Path | None = None,
                  show: bool = True):
    """CSV dosyasından okuyarak grafik çizer."""
    df = pd.read_csv(csv_path)
    plot_flight(df, save_path=save_path, show=show)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Kullanım: python -m analysis.plotter <csv_dosyasi>")
        sys.exit(1)
    plot_from_csv(sys.argv[1])
