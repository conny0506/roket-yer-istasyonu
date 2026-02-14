from math import pi

# Fizik sabitleri
G0 = 9.81            # m/s² — deniz seviyesi yerçekimi
R_EARTH = 6_371_000  # m — Dünya yarıçapı
EARTH_LATITUDE = 39.9  # derece — varsayılan yarışma yeri (Türkiye)

# ISA Atmosfer — deniz seviyesi başlangıç değerleri
RHO0 = 1.225      # kg/m³ — hava yoğunluğu
P0 = 101_325.0    # Pa — basınç
T0 = 288.15       # K — sıcaklık
L = 0.0065        # K/m — troposfer sıcaklık gradyanı
GAS_CONSTANT = 287.05  # J/(kg·K) — kuru hava gaz sabiti

# Roket geometrisi (varsayılan konfigürasyon)
CD = 0.45
DIAMETER = 0.075   # m
CROSS_SECTION_AREA = pi * (DIAMETER / 2) ** 2  # m²

# Motor parametreleri (varsayılan örnek motor)
BURN_TIME = 1.8          # s
DRY_MASS = 2.5           # kg
PROPELLANT_MASS = 0.8    # kg

# Varsayılan itki eğrisi (t_s, F_N) — numpy interpolasyon için
DEFAULT_THRUST_CURVE = [
    (0.00,   0),
    (0.05, 850),
    (0.10, 850),
    (0.30, 620),
    (1.20, 580),
    (1.80,   0),
]

# State machine geçiş eşikleri
LAUNCH_ACCEL_THRESHOLD = 2.0     # g — fırlatma tespiti
ASCENT_MIN_ALTITUDE = 5.0        # m — LAUNCH_DETECT → ASCENT için min irtifa
APOGEE_CONFIRM_STEPS = 3         # ardışık negatif hız adımı → APOGEE onayla
LANDED_ALTITUDE_THRESHOLD = 10.0 # m — DESCENT → LANDED için max irtifa
LANDED_ACCEL_LOW = 0.8           # g — iniş ivme alt sınırı
LANDED_ACCEL_HIGH = 1.2          # g — iniş ivme üst sınırı
ERROR_ACCEL_THRESHOLD = 30.0     # g — bu değer üstü → ERROR
ERROR_ALTITUDE_MIN = -50.0       # m — bu değer altı → ERROR

# Simülasyon parametreleri
DT = 0.01          # s — zaman adımı (10 ms)
MAX_SIM_TIME = 300 # s — simülasyon güvenlik sınırı

# GPS başlangıç koordinatları (varsayılan yarışma yeri)
GPS_LAT0 = 39.9201
GPS_LON0 = 32.8541

# Batarya simülasyonu
BATTERY_FULL_V = 8.4    # V — tam dolu LiPo 2S
BATTERY_DRAIN_RATE = 0.0001  # V/s — yavaş boşalma

# Gürültü modeli — sigma değerleri
ACCEL_NOISE_SIGMA = 0.05     # g
ACCEL_BIAS_DRIFT = 0.0002    # g/s
BARO_NOISE_SIGMA = 0.5       # m
BARO_QUANTIZATION = 0.1      # m — hassasiyet basamağı
GYRO_NOISE_SIGMA = 0.01      # rad/s
GPS_NOISE_SIGMA_M = 3.0      # m — konum hatası (RMS)
