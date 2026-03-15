"""State machine birim testleri."""

import pytest
from simulation.state_machine import FlightState, FlightStateMachine
from simulation.constants import (
    LAUNCH_ACCEL_THRESHOLD,
    ASCENT_MIN_ALTITUDE,
    LANDED_ALTITUDE_THRESHOLD,
    ERROR_ACCEL_THRESHOLD,
)


def make_fsm() -> FlightStateMachine:
    fsm = FlightStateMachine()
    return fsm


def test_initial_state_is_idle():
    fsm = make_fsm()
    assert fsm.state == FlightState.IDLE


def test_arm_transitions_to_armed():
    fsm = make_fsm()
    fsm.arm()
    assert fsm.state == FlightState.ARMED


def test_arm_only_from_idle():
    fsm = make_fsm()
    fsm.arm()
    fsm.arm()  # ikinci arm — ARMED'den ARMED kalmalı, ARMED'dan daha ileri geçmemeli
    assert fsm.state == FlightState.ARMED


def test_launch_detection_on_high_accel():
    fsm = make_fsm()
    fsm.arm()
    state = fsm.update(0.1, altitude=0.0, velocity=1.0,
                       accel_g=LAUNCH_ACCEL_THRESHOLD + 0.5)
    assert state == FlightState.LAUNCH_DETECT


def test_no_launch_on_low_accel():
    fsm = make_fsm()
    fsm.arm()
    state = fsm.update(0.1, altitude=0.0, velocity=0.5,
                       accel_g=LAUNCH_ACCEL_THRESHOLD - 0.5)
    assert state == FlightState.ARMED


def test_launch_detect_to_ascent():
    fsm = make_fsm()
    fsm.arm()
    fsm.update(0.1, altitude=0.0, velocity=1.0, accel_g=3.0)  # LAUNCH_DETECT
    state = fsm.update(0.2, altitude=ASCENT_MIN_ALTITUDE + 1.0,
                       velocity=20.0, accel_g=2.0)
    assert state == FlightState.ASCENT


def test_ascent_to_apogee_on_negative_velocity():
    """APOGEE_CONFIRM_STEPS ardışık negatif hız adımından sonra APOGEE."""
    from simulation.constants import APOGEE_CONFIRM_STEPS
    fsm = make_fsm()
    fsm.arm()
    # LAUNCH_DETECT → ASCENT
    fsm.update(0.1, 0.0, 1.0, 3.0)
    fsm.update(0.2, ASCENT_MIN_ALTITUDE + 1, 20.0, 2.0)
    assert fsm.state == FlightState.ASCENT
    # APOGEE_CONFIRM_STEPS kere negatif hız
    for i in range(APOGEE_CONFIRM_STEPS):
        fsm.update(1.0 + i * 0.01, 500.0, -1.0, 0.5)
    assert fsm.state == FlightState.APOGEE


def test_descent_to_landed():
    fsm = make_fsm()
    fsm.arm()
    fsm.update(0.1, 0.0, 1.0, 3.0)
    fsm.update(0.2, ASCENT_MIN_ALTITUDE + 1, 20.0, 2.0)
    from simulation.constants import APOGEE_CONFIRM_STEPS
    for i in range(APOGEE_CONFIRM_STEPS):
        fsm.update(1.0 + i * 0.01, 500.0, -1.0, 0.5)
    fsm.update(20.0, 100.0, -5.0, 0.6)  # DESCENT
    assert fsm.state == FlightState.DESCENT
    # Yere yakın + 1g ivme → LANDED
    state = fsm.update(60.0, LANDED_ALTITUDE_THRESHOLD - 1,
                       velocity=-0.5, accel_g=1.0)
    assert state == FlightState.LANDED


def test_error_on_excessive_accel():
    fsm = make_fsm()
    fsm.arm()
    state = fsm.update(0.0, 0.0, 0.0, accel_g=ERROR_ACCEL_THRESHOLD + 1)
    assert state == FlightState.ERROR


def test_error_on_negative_altitude():
    fsm = make_fsm()
    fsm.arm()
    state = fsm.update(0.0, altitude=-100.0, velocity=0.0, accel_g=1.0)
    assert state == FlightState.ERROR


def test_state_history_recorded():
    fsm = make_fsm()
    fsm.arm()
    fsm.update(0.1, 0.0, 1.0, 3.0)
    history = fsm.get_state_history()
    states_in_history = [s for _, s in history]
    assert FlightState.ARMED in states_in_history
    assert FlightState.LAUNCH_DETECT in states_in_history


def test_full_flight_sequence():
    """Gerçek simülatör ile tam uçuş — tüm fazlar geçilmeli."""
    from simulation.flight_generator import FlightSimulator, FlightConfig
    sim = FlightSimulator(FlightConfig(noise_seed=0))
    df = sim.run()
    observed_states = set(df["state"].unique())
    expected = {"ARMED", "LAUNCH_DETECT", "ASCENT", "APOGEE", "DESCENT", "LANDED"}
    assert expected.issubset(observed_states), \
        f"Eksik fazlar: {expected - observed_states}"
    assert df["state"].iloc[-1] == "LANDED"
