"""Apogee ve iniş algılama testleri."""

import pytest
from simulation.flight_generator import FlightSimulator, FlightConfig
from simulation.constants import LANDED_ALTITUDE_THRESHOLD


@pytest.fixture(scope="module")
def sim_df():
    """Modül genelinde bir kez simülasyon çalıştır."""
    sim = FlightSimulator(FlightConfig(noise_seed=7))
    return sim.run()


def test_apogee_detected_correctly(sim_df):
    """APOGEE fazı gerçekten en yüksek irtifanın yakınında başlamalı."""
    df = sim_df
    apogee_rows = df[df["state"] == "APOGEE"]
    assert not apogee_rows.empty, "APOGEE fazı hiç başlamadı"

    global_max_alt = df["altitude"].max()
    apogee_start_alt = apogee_rows["altitude"].iloc[0]
    # Apogee fazı en yüksek noktanın %5 içinde başlamalı
    assert apogee_start_alt >= global_max_alt * 0.95, \
        f"Apogee çok erken tespit edildi: {apogee_start_alt:.1f}m / max {global_max_alt:.1f}m"


def test_landed_detection_near_ground(sim_df):
    """LANDED fazındaki irtifa eşiğin altında olmalı (barometrik = site + AGL)."""
    from simulation.flight_generator import FlightConfig
    site_alt = FlightConfig().launch_site_altitude
    df = sim_df
    landed_rows = df[df["state"] == "LANDED"]
    assert not landed_rows.empty, "LANDED fazına hiç ulaşılmadı"
    # Barometrik altitude ≈ site_alt + AGL; AGL < LANDED_ALTITUDE_THRESHOLD + tolerans
    agl_at_landing = landed_rows["altitude"].iloc[0] - site_alt
    assert agl_at_landing <= LANDED_ALTITUDE_THRESHOLD + 5, \
        f"Yere inişten çok önce LANDED tespit edildi: AGL={agl_at_landing:.1f}m"


def test_no_false_apogee_during_ascent(sim_df):
    """ASCENT sırasında APOGEE faz geçişi olmamalı."""
    df = sim_df
    states = df["state"].values
    in_ascent = False
    for s in states:
        if s == "ASCENT":
            in_ascent = True
        elif s == "APOGEE":
            break
        elif in_ascent and s not in ("ASCENT", "APOGEE"):
            pytest.fail(f"ASCENT sırasında beklenmedik faz: {s}")


def test_altitude_monotone_in_ascent(sim_df):
    """ASCENT fazında irtifa genel olarak artmalı (küçük gürültü toleransı ile)."""
    df = sim_df
    ascent = df[df["state"] == "ASCENT"]["altitude"].values
    if len(ascent) < 10:
        pytest.skip("Yeterli ASCENT verisi yok")
    # Yumuşatılmış trend: son değer ilk değerden büyük olmalı
    assert ascent[-1] > ascent[0], "ASCENT sırasında irtifa arttı değil"


def test_noise_doesnt_cause_false_landed_during_descent(sim_df):
    """DESCENT sırasında gürültü nedeniyle erken LANDED geçişi olmamalı."""
    from simulation.flight_generator import FlightConfig
    site_alt = FlightConfig().launch_site_altitude
    df = sim_df
    states = df["state"].values
    altitudes = df["altitude"].values
    for i, s in enumerate(states):
        if s == "LANDED":
            agl = altitudes[i] - site_alt
            assert agl <= LANDED_ALTITUDE_THRESHOLD + 10, \
                f"Yüksek irtifada (AGL={agl:.1f}m) sahte LANDED tespiti"
            break


def test_apogee_altitude_reasonable(sim_df):
    """Apogee irtifası fiziksel olarak makul bir aralıkta olmalı (100m–5000m)."""
    max_alt = sim_df["altitude"].max()
    assert 100 < max_alt < 5000, \
        f"Apogee irtifası ({max_alt:.1f}m) mantıksız aralıkta"


def test_flight_duration_reasonable(sim_df):
    """Toplam uçuş süresi 10s ile 300s arasında olmalı."""
    duration_s = sim_df["timestamp"].iloc[-1] / 1000
    assert 10 < duration_s < 300, \
        f"Uçuş süresi ({duration_s:.1f}s) beklenmedik"
