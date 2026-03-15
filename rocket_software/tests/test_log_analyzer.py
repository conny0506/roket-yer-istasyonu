"""Log analiz aracı testleri."""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from simulation.flight_generator import FlightSimulator, FlightConfig
from analysis.log_analyzer import FlightLogAnalyzer, _REQUIRED_COLUMNS


@pytest.fixture(scope="module")
def sample_csv(tmp_path_factory):
    """Modül genelinde bir kez simülasyon çalıştır, CSV döner."""
    tmp = tmp_path_factory.mktemp("data")
    sim = FlightSimulator(FlightConfig(noise_seed=42))
    df = sim.run()
    path = tmp / "test_flight.csv"
    df.to_csv(path, index=False)
    return path


@pytest.fixture(scope="module")
def analyzer(sample_csv):
    return FlightLogAnalyzer(sample_csv)


# ------------------------------------------------------------------
# Schema
# ------------------------------------------------------------------

def test_schema_validation_passes(analyzer):
    assert FlightLogAnalyzer.validate_schema(analyzer.df)


def test_schema_validation_fails_on_missing_column(sample_csv):
    df = pd.read_csv(sample_csv).drop(columns=["altitude"])
    with pytest.raises(ValueError, match="eksik sütunlar"):
        # Geçici CSV yaz, eksik sütunla yükle
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            df.to_csv(f, index=False)
            fpath = f.name
        try:
            FlightLogAnalyzer(fpath)
        finally:
            os.unlink(fpath)


# ------------------------------------------------------------------
# Apogee tespiti
# ------------------------------------------------------------------

def test_apogee_detection(analyzer):
    alt, t_ms = analyzer.detect_apogee()
    assert alt > 100, "Apogee çok düşük"
    assert alt < 5000, "Apogee çok yüksek"
    assert t_ms > 0


def test_apogee_is_maximum_altitude(analyzer):
    alt, _ = analyzer.detect_apogee()
    assert alt == pytest.approx(analyzer.df["altitude"].max(), abs=0.1)


# ------------------------------------------------------------------
# İniş hızı
# ------------------------------------------------------------------

def test_landing_velocity_is_negative(analyzer):
    v = analyzer.landing_velocity()
    assert v < 0, f"İniş hızı pozitif olmamalı: {v}"


def test_landing_velocity_reasonable(analyzer):
    v = analyzer.landing_velocity()
    # Serbest düşüş → çok büyük negatif; makul aralık
    assert -300 < v < 0, f"İniş hızı ({v}) mantıksız aralıkta"


# ------------------------------------------------------------------
# Faz zaman çizelgesi
# ------------------------------------------------------------------

def test_phase_timeline_complete(analyzer):
    tl = analyzer.phase_timeline()
    phases = set(tl["phase"].values)
    expected = {"ARMED", "LAUNCH_DETECT", "ASCENT", "APOGEE", "DESCENT", "LANDED"}
    assert expected.issubset(phases), f"Eksik fazlar: {expected - phases}"


def test_phase_timeline_columns(analyzer):
    tl = analyzer.phase_timeline()
    assert set(tl.columns) == {"phase", "start_ms", "end_ms", "duration_s"}


def test_phase_durations_positive(analyzer):
    tl = analyzer.phase_timeline()
    assert (tl["duration_s"] >= 0).all()


# ------------------------------------------------------------------
# Anomali tespiti
# ------------------------------------------------------------------

def test_anomaly_accel_spike_detected(sample_csv):
    """Sahte ivme sıçraması enjekte et → tespit edilmeli."""
    df = pd.read_csv(sample_csv).copy()
    df.loc[100, "accel_x"] = 50.0  # ERROR_ACCEL_THRESHOLD üstü
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        df.to_csv(f, index=False)
        fpath = f.name
    try:
        a = FlightLogAnalyzer(fpath)
        anomalies = a.detect_anomalies()
        types = [x["type"] for x in anomalies]
        assert "accel_spike" in types
    finally:
        os.unlink(fpath)


def test_anomaly_baro_freeze_detected(sample_csv):
    """Baro donması enjekte et → tespit edilmeli."""
    df = pd.read_csv(sample_csv).copy()
    # 100 ardışık satırda altitude sabit yap
    freeze_start = 200
    df.loc[freeze_start:freeze_start + 99, "altitude"] = 1500.0
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        df.to_csv(f, index=False)
        fpath = f.name
    try:
        a = FlightLogAnalyzer(fpath)
        anomalies = a.detect_anomalies()
        types = [x["type"] for x in anomalies]
        assert "baro_freeze" in types
    finally:
        os.unlink(fpath)


def test_no_anomalies_in_clean_flight(analyzer):
    """Temiz simülasyon verisinde kritik anomali olmamalı."""
    anomalies = analyzer.detect_anomalies()
    critical = [a for a in anomalies if a["severity"] == "critical"]
    assert len(critical) == 0, f"Beklenmedik kritik anomali: {critical}"


# ------------------------------------------------------------------
# Özet
# ------------------------------------------------------------------

def test_summary_keys_present(analyzer):
    s = analyzer.summary()
    expected_keys = {
        "apogee_altitude_m", "apogee_time_s", "max_velocity_ms",
        "max_accel_g", "landing_velocity_ms", "flight_duration_s",
        "total_steps", "final_state", "phase_durations_s", "anomaly_count",
    }
    assert expected_keys.issubset(set(s.keys()))


def test_summary_final_state_is_landed(analyzer):
    assert analyzer.summary()["final_state"] == "LANDED"


# ------------------------------------------------------------------
# Rapor üretimi
# ------------------------------------------------------------------

def test_report_generates_markdown(analyzer, tmp_path):
    from analysis.report_generator import FlightReport
    report = FlightReport(analyzer)
    md = report.to_markdown()
    assert len(md) > 100
    assert "Apogee" in md
    assert "Faz Zaman Çizelgesi" in md


def test_report_generate_creates_files(sample_csv, tmp_path):
    from analysis.report_generator import generate_report
    result = generate_report(sample_csv, output_dir=tmp_path)
    assert Path(result["report_path"]).exists()
    assert Path(result["plot_path"]).exists()
    assert result["summary"]["apogee_altitude_m"] > 0
