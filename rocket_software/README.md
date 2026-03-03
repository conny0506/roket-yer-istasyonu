# Roket Yazılımı

EuRoC tarzı bir roket yarışması için uçuş simülasyonu, log analizi ve yer istasyonu.

## Hızlı Başlangıç

```bash
cd rocket_software
pip install -r requirements.txt

# 1) Simülasyon — sahte uçuş verisi üret (CSV + grafik)
python -m simulation.flight_generator

# 2) Mevcut bir CSV'yi analiz et / rapor üret
python -m analysis.plotter data/sample_flights/flight_001.csv
python -m analysis.report_generator data/sample_flights/flight_001.csv

# 3) Yer istasyonu (PyQt6 GUI — dahili simülasyon modu)
python -m ground_station.main

# Testler
pytest tests/ -v
```

## Klasör Yapısı

```
simulation/      → Fizik motoru, gürültü modeli, state machine, orkestratör
analysis/        → CSV okuma, apogee tespiti, anomali analizi, rapor üretimi
ground_station/  → PyQt6 yer istasyonu (telemetri + grafik + CesiumJS 3D harita)
tests/           → pytest testleri
data/            → CSV uçuş logları ve raporlar
```

## Fizik Modeli (simulation/)

- Euler veya RK4 integrasyonu (dt = 10ms)
- ISA troposfer atmosferi, irtifaya bağlı yerçekimi
- Aerodinamik sürüntü (sabit Cd, ρ irtifaya göre)
- Değişken kütle (yakıt tükenmesi)
- Sensör gürültüsü: IMU bias drift, baro Gaussian + 0.1m kuantizasyon, GPS RMS jitter
- State machine: IDLE → ARMED → LAUNCH_DETECT → ASCENT → APOGEE → DESCENT → LANDED (+ ERROR)

## Yer İstasyonu (ground_station/)

- **Telemetri paneli** — anlık değerler, batarya/CRC uyarı renkleri
- **Canlı grafikler** — irtifa + hız (2 panel, pyqtgraph, X ekseni bağlı)
- **CesiumJS 3D harita** — uydu görüntüsü, terrain, canlı roket izi, fırlatma noktası seçimi
- **Paket formatı:** `$ROCKET,ts,state,alt,vel,acc,lat,lon,bat,status*CRC` (XOR CRC)
- **Dahili simülasyon modu** — gerçek donanım olmadan FlightSimulator'ı sahte seri port olarak kullanır (`SimBridge`)
- **CSV kayıt** — Aşama 1 ile aynı 16 sütunlu format
- **Hız hesabı** — baro gürültüsü → 21 noktalı rolling mean → türev (gerçekçi profil)

CesiumJS asset'leri `ground_station/assets/` altında yerel servis edilir (CDN bağımlılığı yok).

## Aşamalar

| Aşama | Kapsam | Durum |
|---|---|---|
| 1 | Simülasyon (fizik + gürültü + FSM + CSV) | ✅ |
| 2 | Analiz (apogee, iniş hızı, anomali, rapor) | ✅ |
| 3 | Yer istasyonu (PyQt6 + pyqtgraph + CesiumJS) | ✅ |
| 4 | İleri (Kalman, paraşüt sim, donanım entegrasyonu) | Planlandı |
