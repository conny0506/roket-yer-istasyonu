"""FlightSimulator'ı gerçek zamanlı telemetri paket akışına dönüştürür."""

from __future__ import annotations

import numpy as np
import pandas as pd

from simulation.flight_generator import FlightConfig, FlightSimulator
from simulation.constants import GPS_LAT0, GPS_LON0
from .packet_parser import PacketParser


class SimBridge:
    """pyserial Serial arayüzünü taklit eden simülasyon köprüsü."""

    def __init__(self, config: FlightConfig | None = None):
        self._config = config or FlightConfig()
        self._parser = PacketParser()
        self._df: pd.DataFrame | None = None
        self._idx = 0
        self._open = False
        self._velocity: np.ndarray | None = None
        self._generate()

    def _generate(self):
        sim = FlightSimulator(self._config)
        self._df = sim.run()
        self._open = True
        self._idx = 0
        # Baro türevinden hız hesapla — önce yumuşat, sonra türev al
        alt_raw = self._df["altitude"].values
        ts = self._df["timestamp"].values / 1000.0
        # 21-noktalı pencere ile Savitzky-Golay yumuşatma (~0.2s @ 100Hz)
        alt_smooth = (
            pd.Series(alt_raw)
            .rolling(window=21, center=True, min_periods=1)
            .mean()
            .values
        )
        dt = np.diff(ts, prepend=ts[0])
        dt[dt == 0] = 1e-6
        vel = np.concatenate([[0.0], np.diff(alt_smooth) / dt[1:]])
        self._velocity = vel

    def readline(self) -> bytes:
        """Sıradaki paketi bytes olarak döner. Bittiyse boş bytes."""
        if self._df is None or self._idx >= len(self._df):
            self._open = False
            return b""
        row = self._df.iloc[self._idx]
        vel = float(self._velocity[self._idx])
        accel = float(np.sqrt(
            row["accel_x"] ** 2 + row["accel_y"] ** 2 + row["accel_z"] ** 2
        ))
        status = "ERR" if row["error_code"] == "ERR" else "OK"
        body = (
            f"ROCKET,{int(row['timestamp'])},{row['state']},"
            f"{row['altitude']:.1f},{vel:.2f},{accel:.2f},"
            f"{row['gps_lat']:.6f},{row['gps_lon']:.6f},"
            f"{row['battery_voltage']:.2f},{status}"
        )
        crc = self._parser.calculate_crc(body)
        line = f"${body}*{crc}\n"
        self._idx += 1
        return line.encode("ascii")

    @property
    def is_open(self) -> bool:
        return self._open

    def close(self):
        self._open = False

    def reset(self):
        """Simülasyonu baştan oynat."""
        self._generate()
