"""Ana simülasyon orkestratörü — fizik + gürültü + state machine → CSV."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .constants import (
    CD, CROSS_SECTION_AREA, DIAMETER,
    DRY_MASS, PROPELLANT_MASS, BURN_TIME,
    DT, MAX_SIM_TIME,
    DEFAULT_THRUST_CURVE,
    GPS_LAT0, GPS_LON0,
    BATTERY_FULL_V, BATTERY_DRAIN_RATE,
    G0,
)
from .flight_physics import integrate_euler, integrate_rk4, integrate_euler_2d, thrust_at_time
from .noise_model import NoiseModel
from .state_machine import FlightState, FlightStateMachine


@dataclass
class FlightConfig:
    dry_mass: float = DRY_MASS
    propellant_mass: float = PROPELLANT_MASS
    cd: float = CD
    diameter: float = DIAMETER
    burn_time: float = BURN_TIME
    launch_site_altitude: float = 1000.0  # m — yarışma yeri rakımı
    dt: float = DT
    integration: str = "euler"    # "euler" veya "rk4" (1D); "2d" → balistik 2D
    noise_seed: int = 42
    thrust_curve: list = field(default_factory=lambda: DEFAULT_THRUST_CURVE)
    # Konum
    launch_lat: float = GPS_LAT0
    launch_lon: float = GPS_LON0
    target_lat: float | None = None   # None → dikey atış
    target_lon: float | None = None
    max_tilt_deg: float = 45.0        # dikeyden maksimum sapma (güvenlik)


# ROCKET_PROJECT.md'de tanımlanan CSV sütun sırası
_CSV_COLUMNS = [
    "timestamp", "state",
    "accel_x", "accel_y", "accel_z",
    "gyro_x", "gyro_y", "gyro_z",
    "pressure", "altitude",
    "gps_lat", "gps_lon", "gps_alt",
    "battery_voltage",
    "event_flags", "error_code",
]


class FlightSimulator:
    """Fizik tabanlı uçuş simülatörü."""

    def __init__(self, config: FlightConfig | None = None):
        self.config = config or FlightConfig()
        self._noise = NoiseModel(seed=self.config.noise_seed)
        self._fsm = FlightStateMachine()

    def run(self) -> pd.DataFrame:
        """Simülasyonu başlatır ve uçuş verisini DataFrame olarak döner."""
        cfg = self.config

        # Hedef varsa 2D balistik moda gir
        if cfg.target_lat is not None and cfg.target_lon is not None:
            return self._run_2d()

        integrate = integrate_rk4 if cfg.integration == "rk4" else integrate_euler

        physics_kwargs = dict(
            dry_mass=cfg.dry_mass,
            propellant_mass=cfg.propellant_mass,
            burn_time=cfg.burn_time,
            cd=cfg.cd,
            area=CROSS_SECTION_AREA,
            thrust_curve=cfg.thrust_curve,
        )

        # Başlangıç durumu
        t, h, v = 0.0, 0.0, 0.0
        battery = BATTERY_FULL_V
        rows = []

        self._fsm.arm()

        while t < MAX_SIM_TIME:
            t, h, v, a_true_ms2 = integrate(t, h, v, cfg.dt, **physics_kwargs)
            a_true_g = a_true_ms2 / G0

            state = self._fsm.update(t, h, v, abs(a_true_g))
            battery = max(0.0, battery - BATTERY_DRAIN_RATE * cfg.dt)

            # Sensör okumaları (gürültülü)
            ax = self._noise.accelerometer(a_true_g, cfg.dt)
            ay = self._noise.accelerometer(0.0, cfg.dt)
            az = self._noise.accelerometer(1.0, cfg.dt)  # sabit eksen ~1g
            gx = self._noise.gyroscope(0.0)
            gy = self._noise.gyroscope(0.0)
            gz = self._noise.gyroscope(0.0)
            baro_alt = self._noise.barometer(h + cfg.launch_site_altitude)
            pressure = self._noise.pressure_from_altitude(h + cfg.launch_site_altitude)
            gps_lat, gps_lon = self._noise.gps(cfg.launch_lat, cfg.launch_lon)
            gps_alt = baro_alt + self._noise.barometer(0.0) * 0.2  # GPS irtifa az hassas

            error_code = "OK" if state != FlightState.ERROR else "ERR"
            event_flags = _encode_event_flags(state)

            rows.append({
                "timestamp":       round(t * 1000),   # ms
                "state":           state.name,
                "accel_x":         round(ax, 4),
                "accel_y":         round(ay, 4),
                "accel_z":         round(az, 4),
                "gyro_x":          round(gx, 5),
                "gyro_y":          round(gy, 5),
                "gyro_z":          round(gz, 5),
                "pressure":        round(pressure, 1),
                "altitude":        round(baro_alt, 2),
                "gps_lat":         round(gps_lat, 6),
                "gps_lon":         round(gps_lon, 6),
                "gps_alt":         round(gps_alt, 1),
                "battery_voltage": round(battery, 3),
                "event_flags":     event_flags,
                "error_code":      error_code,
            })

            if self._fsm.is_terminal():
                break

        return pd.DataFrame(rows, columns=_CSV_COLUMNS)

    def _run_2d(self) -> pd.DataFrame:
        """Balistik 2D simülasyon — hedefe doğru azimuth + tilt ile uçar."""
        import math
        cfg = self.config

        # Azimuth + büyük çember mesafesi (launch → target)
        azimuth_rad, distance_m = _bearing_distance(
            cfg.launch_lat, cfg.launch_lon,
            cfg.target_lat, cfg.target_lon,
        )

        physics_kwargs_clean = dict(
            dry_mass=cfg.dry_mass,
            propellant_mass=cfg.propellant_mass,
            burn_time=cfg.burn_time,
            cd=cfg.cd,
            area=CROSS_SECTION_AREA,
            thrust_curve=cfg.thrust_curve,
        )

        def _simulate_range(tilt_r: float) -> float:
            """Verilen tilt için iniş yatay mesafesini döner (gürültüsüz, hızlı)."""
            tt, xx, zz, vvx, vvz = 0.0, 0.0, 0.0, 0.0, 0.0
            steps = 0
            max_steps = int(MAX_SIM_TIME / cfg.dt)
            while steps < max_steps:
                tt, xx, zz, vvx, vvz, _, _ = integrate_euler_2d(
                    tt, xx, zz, vvx, vvz, cfg.dt, tilt_r, **physics_kwargs_clean
                )
                steps += 1
                if zz <= 0.0 and tt > cfg.burn_time + 0.1:
                    break
            return xx

        # Max menzili sim ile tespit et (45° tilt), sonra bisection ile uydur
        max_tilt_rad = math.radians(cfg.max_tilt_deg)
        r_max_real = _simulate_range(max_tilt_rad)

        if distance_m >= r_max_real:
            tilt_rad = max_tilt_rad
        else:
            lo, hi = 0.0, max_tilt_rad
            for _ in range(14):
                mid = 0.5 * (lo + hi)
                if _simulate_range(mid) < distance_m:
                    lo = mid
                else:
                    hi = mid
            tilt_rad = 0.5 * (lo + hi)
        tilt_deg = math.degrees(tilt_rad)

        # Yatay birim vektör (azimuth yönünde, küçük mesafeler için
        # equirectangular yaklaşımı yeterli)
        m_per_deg_lat = 111_320.0
        m_per_deg_lon = m_per_deg_lat * math.cos(math.radians(cfg.launch_lat))

        physics_kwargs = physics_kwargs_clean

        # Başlangıç durumu (x=yatay mesafe, z=AGL)
        t, x, z, vx, vz = 0.0, 0.0, 0.0, 0.0, 0.0
        battery = BATTERY_FULL_V
        rows = []

        self._fsm.arm()

        while t < MAX_SIM_TIME:
            t, x, z, vx, vz, a_axial, a_total = integrate_euler_2d(
                t, x, z, vx, vz, cfg.dt, tilt_rad, **physics_kwargs
            )
            v_total = math.sqrt(vx * vx + vz * vz)
            a_true_g = a_axial / G0
            a_total_g = a_total / G0

            # FSM'e toplam ivme magnitude'unu ver (rest'te ≈ 1g — tilt'ten bağımsız)
            state = self._fsm.update(t, z, vz, a_total_g)
            battery = max(0.0, battery - BATTERY_DRAIN_RATE * cfg.dt)

            # Yatay konumu lat/lon'a çevir
            dlat = (x * math.cos(azimuth_rad)) / m_per_deg_lat
            dlon = (x * math.sin(azimuth_rad)) / m_per_deg_lon
            true_lat = cfg.launch_lat + dlat
            true_lon = cfg.launch_lon + dlon

            ax = self._noise.accelerometer(a_true_g, cfg.dt)
            ay = self._noise.accelerometer(0.0, cfg.dt)
            az_s = self._noise.accelerometer(1.0, cfg.dt)
            gx = self._noise.gyroscope(0.0)
            gy = self._noise.gyroscope(0.0)
            gz = self._noise.gyroscope(0.0)
            baro_alt = self._noise.barometer(z + cfg.launch_site_altitude)
            pressure = self._noise.pressure_from_altitude(z + cfg.launch_site_altitude)
            gps_lat, gps_lon = self._noise.gps(true_lat, true_lon)
            gps_alt = baro_alt + self._noise.barometer(0.0) * 0.2

            error_code = "OK" if state != FlightState.ERROR else "ERR"
            event_flags = _encode_event_flags(state)

            rows.append({
                "timestamp":       round(t * 1000),
                "state":           state.name,
                "accel_x":         round(ax, 4),
                "accel_y":         round(ay, 4),
                "accel_z":         round(az_s, 4),
                "gyro_x":          round(gx, 5),
                "gyro_y":          round(gy, 5),
                "gyro_z":          round(gz, 5),
                "pressure":        round(pressure, 1),
                "altitude":        round(baro_alt, 2),
                "gps_lat":         round(gps_lat, 6),
                "gps_lon":         round(gps_lon, 6),
                "gps_alt":         round(gps_alt, 1),
                "battery_voltage": round(battery, 3),
                "event_flags":     event_flags,
                "error_code":      error_code,
            })

            if self._fsm.is_terminal():
                break

        return pd.DataFrame(rows, columns=_CSV_COLUMNS)

    def save_csv(self, df: pd.DataFrame, path: str | Path) -> Path:
        """DataFrame'i CSV'ye kaydeder, üst klasörü otomatik oluşturur."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        return out

    def get_apogee(self, df: pd.DataFrame) -> tuple:
        """(apogee_altitude_m, apogee_time_ms) döner."""
        idx = df["altitude"].idxmax()
        return df.loc[idx, "altitude"], df.loc[idx, "timestamp"]


def _bearing_distance(lat1: float, lon1: float,
                      lat2: float, lon2: float) -> tuple:
    """Büyük çember azimuth (rad) + mesafe (m). Haversine."""
    import math
    R = 6_371_000.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)

    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    distance = 2 * R * math.asin(math.sqrt(a))

    y = math.sin(dλ) * math.cos(φ2)
    x = math.cos(φ1) * math.sin(φ2) - math.sin(φ1) * math.cos(φ2) * math.cos(dλ)
    azimuth = math.atan2(y, x)  # 0 = kuzey, π/2 = doğu
    return azimuth, distance


def _encode_event_flags(state: FlightState) -> int:
    """Her faz için basit bit bayrağı (bit 0=armed, 1=launch, 2=apogee, 3=landed, 4=error)."""
    flags = {
        FlightState.IDLE: 0x00,
        FlightState.ARMED: 0x01,
        FlightState.LAUNCH_DETECT: 0x02,
        FlightState.ASCENT: 0x02,
        FlightState.APOGEE: 0x04,
        FlightState.DESCENT: 0x04,
        FlightState.LANDED: 0x08,
        FlightState.ERROR: 0x10,
    }
    return flags.get(state, 0x00)


def main():
    """Demo: simülasyonu çalıştır, CSV kaydet, özet yazdır."""
    import time

    config = FlightConfig(integration="euler")
    sim = FlightSimulator(config)

    print("Simülasyon başlatılıyor...")
    t0 = time.perf_counter()
    df = sim.run()
    elapsed = time.perf_counter() - t0

    out_dir = Path(__file__).parent.parent / "data" / "sample_flights"
    out_path = sim.save_csv(df, out_dir / "flight_001.csv")

    apogee_alt, apogee_t = sim.get_apogee(df)
    duration_s = df["timestamp"].iloc[-1] / 1000

    print(f"Simülasyon tamamlandı ({elapsed:.2f}s hesaplama süresi)")
    print(f"  Toplam süre  : {duration_s:.1f} s ({len(df)} adım)")
    print(f"  Apogee       : {apogee_alt:.1f} m @ t={apogee_t/1000:.2f}s")
    print(f"  Son faz      : {df['state'].iloc[-1]}")
    print(f"  CSV kaydedildi: {out_path}")

    # Grafik üret
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from analysis.plotter import plot_flight
        plot_flight(df)
    except ImportError:
        print("(matplotlib yüklü değil, grafik atlandı)")


if __name__ == "__main__":
    main()
