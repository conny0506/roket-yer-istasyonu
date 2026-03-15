"""CSV uçuş logu analiz aracı."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from simulation.constants import (
    ERROR_ACCEL_THRESHOLD,
    LANDED_ALTITUDE_THRESHOLD,
)

_REQUIRED_COLUMNS = {
    "timestamp", "state", "accel_x", "accel_y", "accel_z",
    "pressure", "altitude", "gps_lat", "gps_lon", "battery_voltage",
}

_BARO_FREEZE_WINDOW = 50   # ardışık adım sayısı
_BATTERY_LOW_V = 7.0       # V
_GPS_FREEZE_WINDOW = 100   # adım


class FlightLogAnalyzer:
    """Uçuş CSV logunu okur, analiz eder."""

    def __init__(self, csv_path: str | Path):
        self.csv_path = Path(csv_path)
        self.df = pd.read_csv(self.csv_path)
        if not self.validate_schema(self.df):
            missing = _REQUIRED_COLUMNS - set(self.df.columns)
            raise ValueError(f"CSV'de eksik sütunlar: {missing}")
        self._time_s = self.df["timestamp"].values / 1000.0

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    @staticmethod
    def validate_schema(df: pd.DataFrame) -> bool:
        return _REQUIRED_COLUMNS.issubset(set(df.columns))

    # ------------------------------------------------------------------
    # Temel tespitler
    # ------------------------------------------------------------------

    def detect_apogee(self) -> tuple:
        """(apogee_altitude_m, time_ms) döner."""
        idx = self.df["altitude"].idxmax()
        return float(self.df.loc[idx, "altitude"]), int(self.df.loc[idx, "timestamp"])

    def landing_velocity(self) -> float:
        """DESCENT fazının son 1 saniyesindeki ortalama dikey hız (m/s)."""
        descent = self.df[self.df["state"] == "DESCENT"]
        if len(descent) < 2:
            return 0.0
        t_end = descent["timestamp"].iloc[-1]
        last_sec = descent[descent["timestamp"] >= t_end - 1000]
        if len(last_sec) < 2:
            last_sec = descent.tail(10)
        alt = last_sec["altitude"].values
        t = last_sec["timestamp"].values / 1000.0
        if len(t) < 2 or (t[-1] - t[0]) == 0:
            return 0.0
        return float((alt[-1] - alt[0]) / (t[-1] - t[0]))

    def phase_timeline(self) -> pd.DataFrame:
        """Her faz için başlangıç, bitiş, süre bilgisi."""
        rows = []
        states = self.df["state"].values
        timestamps = self.df["timestamp"].values
        i = 0
        while i < len(states):
            j = i + 1
            while j < len(states) and states[j] == states[i]:
                j += 1
            t_start = int(timestamps[i])
            t_end = int(timestamps[j - 1])
            rows.append({
                "phase":       states[i],
                "start_ms":    t_start,
                "end_ms":      t_end,
                "duration_s":  round((t_end - t_start) / 1000.0, 2),
            })
            i = j
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Özet
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        """Uçuşun temel istatistiklerini döner."""
        apogee_alt, apogee_t = self.detect_apogee()
        land_v = self.landing_velocity()
        timeline = self.phase_timeline()
        duration_s = self.df["timestamp"].iloc[-1] / 1000.0

        accel_mag = np.sqrt(
            self.df["accel_x"] ** 2 +
            self.df["accel_y"] ** 2 +
            self.df["accel_z"] ** 2
        )

        # Baro türevinden hız tahmini
        alt = self.df["altitude"].values
        dt = np.diff(self._time_s)
        dt[dt == 0] = 1e-6
        vel = np.diff(alt) / dt
        max_velocity = float(np.max(vel)) if len(vel) > 0 else 0.0

        phase_durations = {}
        for _, row in timeline.iterrows():
            phase_durations[row["phase"]] = row["duration_s"]

        return {
            "apogee_altitude_m":  round(apogee_alt, 1),
            "apogee_time_s":      round(apogee_t / 1000, 2),
            "max_velocity_ms":    round(max_velocity, 1),
            "max_accel_g":        round(float(accel_mag.max()), 2),
            "landing_velocity_ms": round(land_v, 2),
            "flight_duration_s":  round(duration_s, 1),
            "total_steps":        len(self.df),
            "final_state":        self.df["state"].iloc[-1],
            "phase_durations_s":  phase_durations,
            "anomaly_count":      len(self.detect_anomalies()),
        }

    # ------------------------------------------------------------------
    # Anomali tespiti
    # ------------------------------------------------------------------

    def detect_anomalies(self) -> list:
        """Sensör anomalilerini tespit eder. Her biri dict döner."""
        anomalies = []
        anomalies += self._detect_accel_spikes()
        anomalies += self._detect_baro_freeze()
        anomalies += self._detect_gps_loss()
        anomalies += self._detect_low_battery()
        anomalies.sort(key=lambda x: x["time_ms"])
        return anomalies

    def _detect_accel_spikes(self) -> list:
        results = []
        accel_mag = np.sqrt(
            self.df["accel_x"] ** 2 +
            self.df["accel_y"] ** 2 +
            self.df["accel_z"] ** 2
        ).values
        mask = accel_mag > ERROR_ACCEL_THRESHOLD
        idxs = np.where(mask)[0]
        for idx in idxs:
            results.append({
                "type":     "accel_spike",
                "time_ms":  int(self.df["timestamp"].iloc[idx]),
                "value":    round(float(accel_mag[idx]), 2),
                "severity": "critical",
            })
        return results

    def _detect_baro_freeze(self) -> list:
        results = []
        alt = self.df["altitude"].values
        i = 0
        while i < len(alt) - _BARO_FREEZE_WINDOW:
            window = alt[i:i + _BARO_FREEZE_WINDOW]
            if np.ptp(window) == 0.0:  # max - min = 0 → donmuş
                results.append({
                    "type":     "baro_freeze",
                    "time_ms":  int(self.df["timestamp"].iloc[i]),
                    "value":    round(float(alt[i]), 2),
                    "severity": "warning",
                })
                i += _BARO_FREEZE_WINDOW  # çakışan uyarıları atla
            else:
                i += 1
        return results

    def _detect_gps_loss(self) -> list:
        results = []
        lat = self.df["gps_lat"].values
        lon = self.df["gps_lon"].values
        i = 0
        while i < len(lat) - _GPS_FREEZE_WINDOW:
            lat_w = lat[i:i + _GPS_FREEZE_WINDOW]
            lon_w = lon[i:i + _GPS_FREEZE_WINDOW]
            if np.ptp(lat_w) == 0.0 and np.ptp(lon_w) == 0.0:
                results.append({
                    "type":     "gps_loss",
                    "time_ms":  int(self.df["timestamp"].iloc[i]),
                    "value":    f"lat={lat[i]:.4f} lon={lon[i]:.4f}",
                    "severity": "warning",
                })
                i += _GPS_FREEZE_WINDOW
            else:
                i += 1
        return results

    def _detect_low_battery(self) -> list:
        results = []
        batt = self.df["battery_voltage"].values
        timestamps = self.df["timestamp"].values
        in_low = False
        for i, v in enumerate(batt):
            if v < _BATTERY_LOW_V and not in_low:
                results.append({
                    "type":     "low_battery",
                    "time_ms":  int(timestamps[i]),
                    "value":    round(float(v), 3),
                    "severity": "warning",
                })
                in_low = True
            elif v >= _BATTERY_LOW_V:
                in_low = False
        return results
