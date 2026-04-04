"""$ROCKET telemetri paketi parse ve CRC doğrulama."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class TelemetryPacket:
    timestamp_ms: int
    state: str
    altitude: float
    velocity: float
    accel: float
    lat: float
    lon: float
    battery: float
    status: str        # "OK" | "WARN" | "ERR"
    crc_valid: bool
    raw: str


class PacketParser:
    """$ROCKET,... formatındaki telemetri paketlerini parse eder."""

    PREFIX = "$ROCKET"
    FIELD_COUNT = 10   # $ dahil 10 virgülle ayrılmış alan

    @staticmethod
    def calculate_crc(data: str) -> str:
        """$ ile * arasındaki (hariç) tüm karakterlerin XOR CRC'si."""
        crc = 0
        for ch in data:
            crc ^= ord(ch)
        return f"{crc:02X}"

    def parse(self, line: str) -> TelemetryPacket | None:
        """Ham satırı TelemetryPacket'e dönüştürür. Geçersizse None döner."""
        line = line.strip()
        if not line.startswith(self.PREFIX):
            return None

        # CRC ayır: "...*4F"
        if "*" not in line:
            return None
        body, crc_str = line.rsplit("*", 1)
        crc_str = crc_str.strip()

        # $ hariç body'nin CRC'sini hesapla
        inner = body[1:]  # '$' karakterini çıkar
        expected_crc = self.calculate_crc(inner)
        crc_valid = (crc_str.upper() == expected_crc.upper())

        # Alan parse
        try:
            fields = body.split(",")
            if len(fields) != self.FIELD_COUNT:
                return None
            _, ts, state, alt, vel, acc, lat, lon, batt, status = fields
            return TelemetryPacket(
                timestamp_ms=int(ts),
                state=state.strip(),
                altitude=float(alt),
                velocity=float(vel),
                accel=float(acc),
                lat=float(lat),
                lon=float(lon),
                battery=float(batt),
                status=status.strip(),
                crc_valid=crc_valid,
                raw=line,
            )
        except (ValueError, IndexError):
            return None

    @staticmethod
    def format_packet(p: TelemetryPacket) -> str:
        """TelemetryPacket'i wire formatına dönüştürür."""
        body = (
            f"ROCKET,{p.timestamp_ms},{p.state},"
            f"{p.altitude:.1f},{p.velocity:.2f},{p.accel:.2f},"
            f"{p.lat:.6f},{p.lon:.6f},{p.battery:.2f},{p.status}"
        )
        crc = PacketParser.calculate_crc(body)
        return f"${body}*{crc}"
