# 🚀 Roket Takımı — Yazılım Projesi

## Proje Özeti
Bir roket yarışması (muhtemelen EuRoC) için uçuş simülasyonu, log analizi ve yer istasyonu yazılımı geliştiriyoruz. Takıma yeni katılındı, yazılım kısmı sıfırdan inşa edilecek.

---

## Tech Stack

| Alan | Teknoloji |
|---|---|
| Simülasyon & Analiz | Python |
| Arayüz (Yer İstasyonu) | Python + PyQt6 |
| Gerçek Zamanlı Grafik | pyqtgraph |
| Seri Port Haberleşme | pyserial |
| Matematiksel Hesaplama | numpy, scipy |
| Veri Analizi | pandas |
| Görselleştirme | matplotlib |
| IDE | VS Code |

---

## Klasör Yapısı

```
rocket_software/
├── simulation/
│   ├── flight_generator.py       # Sahte uçuş verisi üretici
│   ├── state_machine.py          # Uçuş fazı tespiti
│   ├── noise_model.py            # Sensör gürültüsü simülasyonu
│   └── flight_physics.py         # Temel fizik hesaplamaları
│
├── analysis/
│   ├── log_analyzer.py           # CSV log dosyası analizi
│   ├── plotter.py                # Grafik üretimi
│   └── report_generator.py      # Uçuş sonrası rapor
│
├── ground_station/
│   ├── main.py                   # Yer istasyonu giriş noktası
│   ├── ui/
│   │   ├── main_window.py        # Ana PyQt6 penceresi (orkestratör)
│   │   ├── altitude_widget.py    # Canlı irtifa + hız grafiği (2 panel)
│   │   ├── telemetry_panel.py    # Telemetri veri paneli
│   │   └── map_widget.py         # CesiumJS 3D harita (QWebEngineView)
│   ├── core/
│   │   ├── serial_handler.py     # Seri port bağlantısı (QThread)
│   │   ├── packet_parser.py      # $ROCKET paket çözümleme + XOR CRC
│   │   ├── sim_bridge.py         # FlightSimulator → sahte seri port köprüsü
│   │   └── data_recorder.py      # CSV'ye kayıt
│   └── assets/                   # Cesium.js, widgets.css, qwebchannel.js, map_template.html
│
├── tests/
│   ├── test_state_machine.py
│   ├── test_packet_parser.py
│   └── test_altitude_detection.py
│
├── data/
│   ├── sample_flights/           # Örnek uçuş CSV'leri
│   └── logs/                     # Gerçek uçuş logları
│
├── docs/
│   ├── Flight_Software_Test_Plan.md
│   └── Telemetry_Packet_Format.md
│
├── requirements.txt
└── README.md
```

---

## Fizik Modeli

Simülasyon gerçek fiziksel etkenler modellenerek yapılır. Katmanlı yaklaşım uygulanır — önce basit, sonra gerçeğe yaklaştırılır.

### Temel Denklem (Her Zaman Adımında)

```
F_net = F_itki(t) - F_drag(v, h) - F_yerçekimi(m, h)

a = F_net / m(t)      # ivme
v = v + a × dt        # hız güncelle
h = h + v × dt        # irtifa güncelle
```

### 1. Yerçekimi

```python
# Basit model
g = 9.81  # m/s²

# Gelişmiş model (irtifaya göre değişen)
g(h) = 9.780 × (1 + 0.0053 × sin²(enlem)) × (R / (R + h))²
```

### 2. Aerodinamik Sürüntü (Drag)

```python
F_drag = 0.5 × rho(h) × v² × Cd × A

# rho(h) = irtifaya göre hava yoğunluğu  (kg/m³)
# Cd     = sürükleme katsayısı           (roket geometrisine göre ~0.3–0.6)
# A      = roketin kesit alanı           (m²)
```

### 3. Atmosfer Modeli — ISA (International Standard Atmosphere)

| İrtifa | Hava Yoğunluğu | Basınç |
|---|---|---|
| 0 m (deniz seviyesi) | 1.225 kg/m³ | 101325 Pa |
| 1000 m | 1.112 kg/m³ | 89876 Pa |
| 3000 m | 0.909 kg/m³ | 70121 Pa |
| 5000 m | 0.736 kg/m³ | 54048 Pa |

scipy ile `ambiance` kütüphanesi ISA modelini hazır verir.

### 4. Motor İtki Eğrisi (Thrust Curve)

Motor her saniye aynı itkiyi vermez, gerçek eğri ThrustCurve.org'dan indirilir:

```
0.0s → 0 N
0.1s → 850 N   ← ani ateşleme
0.3s → 620 N
1.2s → 580 N
1.8s → 0 N     ← yakıt bitti
```

Dosya formatı: `.eng` veya `.rse` — numpy ile interpolasyon yapılarak okunur.

### 5. Kütle Değişimi

```python
m(t) = m_kuru + m_yakit × (1 - t / yanma_suresi)
# Yakıt yandıkça roket hafifler → ivme artar
```

### 6. Hava Koşulları

| Parametre | Modeldeki Etkisi | Uygulama |
|---|---|---|
| Rüzgar hızı | Yatay sürükleme kuvveti | `F_wind = 0.5 × rho × v_wind² × Cd × A` |
| Rüzgar yönü | 3 eksen sapmaya sebep olur | Vektörel hesap |
| Sıcaklık | Hava yoğunluğunu etkiler → drag değişir | ISA sıcaklık profili |
| Yarışma yeri rakımı | Başlangıç hava yoğunluğunu değiştirir | Başlangıç koşulu olarak girilir |
| Nem | Çok küçük etki | İhmal edilebilir |

### 7. Sayısal İntegrasyon Yöntemi

```
Basit   → Euler (dt = 10ms) — başlangıç için yeterli
Gelişmiş → Runge-Kutta RK4  — daha hassas, scipy ile hazır
```

### 8. Simülasyon Katmanları

```
Katman 1 (Başlangıç):
  Euler + sabit drag + ISA atmosfer + sabit yerçekimi

Katman 2 (Orta):
  RK4 + değişken Cd + gerçek motor eğrisi + kütle değişimi

Katman 3 (Gelişmiş):
  RocketPy entegrasyonu + rüzgar + 3 eksen + yarışma yeri koordinatları
```

### 9. Kullanılan Kütüphaneler

| Kütüphane | Kullanım Amacı |
|---|---|
| `numpy` | Vektörel hesaplama, interpolasyon |
| `scipy` | RK4 integrasyon, filtreleme |
| `ambiance` | ISA atmosfer modeli |
| `rocketpy` | Hazır roket simülasyon motoru |

```
pip install rocketpy ambiance
```

---

## Uçuş Fazları (State Machine)

```
IDLE → ARMED → LAUNCH_DETECT → ASCENT → APOGEE → DESCENT → LANDED → (ERROR)
```

| Faz | Tetikleyici Koşul |
|---|---|
| IDLE | Sistem başladı, bekliyor |
| ARMED | Manuel komut ile hazır |
| LAUNCH_DETECT | İvme > 2g ve yükseliyor |
| ASCENT | İrtifa artıyor |
| APOGEE | İrtifa düşmeye başladı |
| DESCENT | İrtifa azalıyor |
| LANDED | İrtifa < 10m ve ivme ~1g |
| ERROR | Sensör verisi geçersiz |

---

## Telemetri Paket Formatı

```
$ROCKET,<timestamp>,<state>,<altitude>,<velocity>,<accel>,<lat>,<lon>,<battery>,<status>*<CRC>
```

**Örnek:**
```
$ROCKET,12500,ASCENT,243.5,51.2,3.91,39.9201,32.8541,7.8,OK*4F
```

| Alan | Açıklama | Birim |
|---|---|---|
| timestamp | Uçuştan itibaren geçen süre | ms |
| state | Uçuş fazı | string |
| altitude | Barometrik irtifa | metre |
| velocity | Dikey hız | m/s |
| accel | İvme büyüklüğü | g |
| lat/lon | GPS koordinatları | derece |
| battery | Batarya voltajı | V |
| status | Sistem durumu | OK / WARN / ERR |
| CRC | Veri doğrulama | hex |

---

## Log Dosyası Formatı (CSV)

```csv
timestamp,state,accel_x,accel_y,accel_z,gyro_x,gyro_y,gyro_z,pressure,altitude,gps_lat,gps_lon,gps_alt,battery_voltage,event_flags,error_code
```

---

## Geliştirme Aşamaları

### Aşama 1 — Simülasyon ✅
- [x] Sahte uçuş verisi üretici (numpy ile fizik tabanlı, Euler + RK4)
- [x] Sensör gürültüsü modeli (IMU bias drift, baro Gaussian + kuantizasyon, GPS jitter)
- [x] State machine implementasyonu (IDLE → ARMED → LAUNCH_DETECT → ASCENT → APOGEE → DESCENT → LANDED + ERROR)
- [x] CSV çıktısı üretimi (16 sütunlu standart format)
- [x] Matplotlib ile uçuş grafiği

### Aşama 2 — Analiz Araçları ✅
- [x] CSV log okuyucu
- [x] Apogee tespiti algoritması
- [x] İniş hızı hesaplama
- [x] Uçuş fazı zaman çizelgesi
- [x] Anomali tespiti (sensör çıkması, bağlantı kopması)
- [x] Otomatik markdown rapor üretimi (`FlightReport.to_text()`)

### Aşama 3 — Yer İstasyonu Arayüzü ✅
- [x] PyQt6 ana pencere (telemetri + grafik + harita layout)
- [x] Pyqtgraph ile canlı irtifa **ve hız** grafiği (2 panel, X ekseni bağlı)
- [x] Telemetri paneli (tüm değerler anlık, batarya/CRC uyarı renkleri)
- [x] Pyserial ile seri port bağlantısı (QThread tabanlı)
- [x] Paket parser ($ROCKET formatı, XOR CRC doğrulama)
- [x] CSV'ye otomatik kayıt (Aşama 1 ile aynı sütun düzeni)
- [x] Batarya düşük / bağlantı koptu uyarıları
- [x] **Dahili simülasyon modu** — `SimBridge` ile FlightSimulator'ı sahte seri port olarak kullanır
- [x] **CesiumJS 3D harita** (QWebEngineView + QWebChannel) — uydu görüntüsü, terrain, canlı roket izi, fırlatma noktası seçimi
- [x] Apogee 3D işaretçisi

### Aşama 4 — İleri Özellikler
- [ ] Kalman filtresi (irtifa + hız için)
- [ ] Çoklu uçuş karşılaştırması
- [ ] Paraşüt deploy simülasyonu (şu an freefall → -110 m/s terminal hız)
- [ ] Gerçek donanım (ESP32/STM32) entegrasyon testleri

---

## Test Planı

Her modül için şu testler yazılacak:

| Test Türü | Araç |
|---|---|
| Birim testi | pytest |
| Simülasyon testi | Sahte CSV verisi |
| Paket parse testi | Hatalı paket senaryoları |
| State machine testi | Tüm faz geçişleri |

---

## Requirements (requirements.txt)

```
numpy>=1.24.0
scipy>=1.10.0
pandas>=2.0.0
matplotlib>=3.7.0
PyQt6>=6.5.0
PyQt6-WebEngine>=6.5.0
pyqtgraph>=0.13.0
pyserial>=3.5
pytest>=7.0.0
rocketpy>=1.0.0
ambiance>=1.2.0
```

---

## Geliştirme Kuralları

- `main` branch her zaman çalışır durumda olmalı
- Her özellik ayrı branch'te geliştirilmeli
- Tüm fonksiyonlara docstring yazılmalı
- `delay()` / `time.sleep()` yerine zamanlayıcı tabanlı döngü kullanılmalı
- Magic number kullanma, sabitler için `constants.py` oluştur
- Her commit sonrası testler çalıştırılmalı

---

## Notlar

- Yarışma kuralları netleşince telemetri frekansı ve frekans bandı güncellenmeli
- Gerçek donanım (ESP32/STM32) entegrasyonu Aşama 3 sonrasında yapılacak

---

## Yer İstasyonu — Tasarım Notları (Aşama 3)

### Veri Akışı

```
FlightSimulator → SimBridge.readline() → SerialHandler(QThread)
    → PacketParser.parse() → TelemetryPacket
    → MainWindow._on_packet():
        ├── TelemetryPanel.update()
        ├── AltitudeWidget.update_data()      (irtifa + hız grafiği)
        ├── MapWidget.update_position()       (CesiumJS billboard + trail)
        └── DataRecorder.record()             (CSV)
```

Paket hızı: **100 Hz** (`SerialHandler.msleep(10)`).

### Paket Formatı

```
$ROCKET,<ts_ms>,<state>,<altitude>,<velocity>,<accel>,<lat>,<lon>,<battery>,<status>*<CRC>
```

CRC: `$` ile `*` arasındaki tüm karakterlerin XOR'u, 2 haneli uppercase hex.

### Hız Hesaplama (SimBridge)

Barometrik irtifa çok gürültülü olduğu için ham türev kullanılamaz (±0.5m baro gürültüsü × 100 Hz = ±50 m/s salınım). Çözüm:

```python
alt_smooth = pd.Series(alt_raw).rolling(window=21, center=True, min_periods=1).mean()
velocity = np.diff(alt_smooth) / dt
```

21 noktalı pencere (~0.2s @ 100Hz) → fiziksel olarak gerçekçi düz hız profili.

### CesiumJS Harita Mimarisi

`QUrl.fromLocalFile()` ile `file://` üzerinden açılınca tarayıcı CDN'lere erişimi engelliyor. Çözüm: **localhost HTTP sunucusu** (`http.server.SimpleHTTPRequestHandler` daemon thread).

Asset'ler **yerel** olarak servis edilir (CDN bağımlılığı yok, GoodbyeDPI vb. DPI araçları engelleyemez):
- `ground_station/assets/Cesium.js` (~4.9 MB)
- `ground_station/assets/widgets.css` (~29 KB)
- `ground_station/assets/qwebchannel.js` (16 KB, Qt resource'undan çıkarılmış)
- `ground_station/assets/map_template.html`

CesiumJS API: `Cesium.Terrain.fromWorldTerrain()` (v1.107+ — eski `createWorldTerrain()` kaldırıldı).

Roket ikonu: emoji 🚀 → HTML5 canvas → data URL (CesiumJS billboard `image` doğrudan emoji string kabul etmiyor).

Python ↔ JS köprüsü: `QWebChannel` + `_MapBridge(QObject)`. Kullanıcı haritaya tıklayınca JS `pybridge.setLaunchPoint(lat, lon)` çağırır → Python tarafında `launch_point_selected` sinyali yayılır.

### Grafik Penceresi

`AltitudeWidget._MAX_POINTS = 60_000` (10 dakika @ 100Hz) — tüm uçuş tek ekranda kalır. Önceki 600 değeri scroll problemine yol açıyordu (6s'lik kayan pencere → tırmanış + apogee ekrandan düşüyordu).

### Bilinen Sınırlamalar

- Paraşüt simülasyonu yok → freefall, terminal hız ~-110 m/s.
- Fizik AGL üzerinden çalışıyor, baro_alt = AGL + `launch_site_altitude` (varsayılan 1000m MSL). Apogee etiketi MSL gösterir.
- Yere çarpma anında `v_new = 0` artificially atanır → hız grafiğinin son birkaç örneğinde yumuşatma kenar efekti (küçük bump) görünür.
- Uçuş öncesi checklist belgesi ayrıca hazırlanacak
