"""Alınan telemetri paketlerini CSV'ye kaydeder."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .packet_parser import TelemetryPacket

_CSV_COLUMNS = [
    "timestamp", "state",
    "accel_x", "accel_y", "accel_z",
    "gyro_x", "gyro_y", "gyro_z",
    "pressure", "altitude",
    "gps_lat", "gps_lon", "gps_alt",
    "battery_voltage", "event_flags", "error_code",
]

_FLUSH_EVERY = 50  # paket


class DataRecorder:
    """Paketleri Aşama 1 CSV formatıyla kaydeder."""

    def __init__(self, output_dir: str | Path):
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        fname = f"flight_{datetime.now():%Y%m%d_%H%M%S}.csv"
        self._path = out / fname
        self._file = open(self._path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=_CSV_COLUMNS)
        self._writer.writeheader()
        self._count = 0

    def record(self, packet: TelemetryPacket):
        row = {
            "timestamp":       packet.timestamp_ms,
            "state":           packet.state,
            "accel_x":         round(packet.accel, 4),
            "accel_y":         0.0,
            "accel_z":         1.0,
            "gyro_x":          0.0,
            "gyro_y":          0.0,
            "gyro_z":          0.0,
            "pressure":        0.0,
            "altitude":        round(packet.altitude, 2),
            "gps_lat":         round(packet.lat, 6),
            "gps_lon":         round(packet.lon, 6),
            "gps_alt":         round(packet.altitude, 1),
            "battery_voltage": round(packet.battery, 3),
            "event_flags":     0,
            "error_code":      "ERR" if packet.status == "ERR" else "OK",
        }
        self._writer.writerow(row)
        self._count += 1
        if self._count % _FLUSH_EVERY == 0:
            self._file.flush()

    def close(self):
        if not self._file.closed:
            self._file.flush()
            self._file.close()

    def get_path(self) -> Path:
        return self._path

    @property
    def packet_count(self) -> int:
        return self._count

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
