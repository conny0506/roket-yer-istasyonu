"""Gerçekçi IMU ve barometrik sensör gürültüsü modeli."""

import numpy as np
from .constants import (
    ACCEL_NOISE_SIGMA, ACCEL_BIAS_DRIFT,
    BARO_NOISE_SIGMA, BARO_QUANTIZATION,
    GYRO_NOISE_SIGMA,
    GPS_NOISE_SIGMA_M,
    GPS_LAT0, GPS_LON0,
)

_METERS_PER_DEGREE_LAT = 111_320.0


class NoiseModel:
    """Tekrar üretilebilir gürültü modeli. Seed ile başlatılır."""

    def __init__(self, seed: int = 42):
        self._rng = np.random.default_rng(seed)
        self._accel_bias = 0.0  # g — zamanla driftle

    def accelerometer(self, accel_true_g: float, dt: float) -> float:
        """IMU ivmemetre gürültüsü (g cinsinden). Bias drift dahil."""
        self._accel_bias += self._rng.normal(0.0, ACCEL_BIAS_DRIFT * dt)
        noise = self._rng.normal(0.0, ACCEL_NOISE_SIGMA)
        return accel_true_g + noise + self._accel_bias

    def barometer(self, altitude_true_m: float) -> float:
        """Barometrik irtifa ölçümü (m). Gaussian gürültü + kuantizasyon."""
        noisy = altitude_true_m + self._rng.normal(0.0, BARO_NOISE_SIGMA)
        # Sensor hassasiyeti — 0.1m basamak
        return round(noisy / BARO_QUANTIZATION) * BARO_QUANTIZATION

    def gyroscope(self, rate_true_rads: float) -> float:
        """Jiroskop ölçümü (rad/s)."""
        return rate_true_rads + self._rng.normal(0.0, GYRO_NOISE_SIGMA)

    def gps(self, lat: float = GPS_LAT0, lon: float = GPS_LON0) -> tuple:
        """GPS konum gürültüsü. (lat, lon) döner. Sigma: GPS_NOISE_SIGMA_M metre."""
        meters_per_degree_lon = _METERS_PER_DEGREE_LAT * np.cos(np.radians(lat))
        delta_lat = self._rng.normal(0.0, GPS_NOISE_SIGMA_M) / _METERS_PER_DEGREE_LAT
        delta_lon = self._rng.normal(0.0, GPS_NOISE_SIGMA_M) / meters_per_degree_lon
        return lat + delta_lat, lon + delta_lon

    def pressure_from_altitude(self, altitude_m: float) -> float:
        """ISA basınç değerini gürültüyle döner (Pa)."""
        from .constants import P0, T0, L, G0, GAS_CONSTANT
        temp = max(T0 - L * altitude_m, 1.0)
        pressure_true = P0 * (temp / T0) ** (G0 / (L * GAS_CONSTANT))
        noise = self._rng.normal(0.0, 50.0)  # ±50 Pa gürültü
        return max(pressure_true + noise, 0.0)
