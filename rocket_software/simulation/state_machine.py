"""Uçuş fazı durum makinesi (FSM)."""

from enum import Enum, auto
from .constants import (
    LAUNCH_ACCEL_THRESHOLD,
    ASCENT_MIN_ALTITUDE,
    APOGEE_CONFIRM_STEPS,
    LANDED_ALTITUDE_THRESHOLD,
    LANDED_ACCEL_LOW,
    LANDED_ACCEL_HIGH,
    ERROR_ACCEL_THRESHOLD,
    ERROR_ALTITUDE_MIN,
)


class FlightState(Enum):
    IDLE = auto()
    ARMED = auto()
    LAUNCH_DETECT = auto()
    ASCENT = auto()
    APOGEE = auto()
    DESCENT = auto()
    LANDED = auto()
    ERROR = auto()


class FlightStateMachine:
    """Her zaman adımında `update()` çağrılır, mevcut faz döner."""

    def __init__(self):
        self.state = FlightState.IDLE
        self._neg_velocity_count = 0  # APOGEE onaylama sayacı
        self._history: list = []      # [(time_s, FlightState)]

    def arm(self, time_s: float = 0.0):
        """Sistemi ARMED fazına geçirir. Yalnızca IDLE'dan çağrılabilir."""
        if self.state == FlightState.IDLE:
            self.state = FlightState.ARMED
            self._history.append((time_s, FlightState.ARMED))

    def update(self, time_s: float, altitude: float,
               velocity: float, accel_g: float) -> FlightState:
        """Sensör değerleri ile faz geçişini değerlendir. Mevcut fazı döner."""
        new_state = self._transition(altitude, velocity, accel_g)
        if new_state != self.state:
            self._history.append((time_s, new_state))
            self.state = new_state
        return self.state

    def _transition(self, altitude: float, velocity: float,
                    accel_g: float) -> FlightState:
        # Herhangi bir fazdan ERROR'a geçiş kontrolü
        if accel_g > ERROR_ACCEL_THRESHOLD or altitude < ERROR_ALTITUDE_MIN:
            return FlightState.ERROR

        s = self.state

        if s == FlightState.IDLE:
            return FlightState.IDLE

        if s == FlightState.ARMED:
            if accel_g > LAUNCH_ACCEL_THRESHOLD:
                return FlightState.LAUNCH_DETECT
            return FlightState.ARMED

        if s == FlightState.LAUNCH_DETECT:
            if velocity > 0 and altitude > ASCENT_MIN_ALTITUDE:
                return FlightState.ASCENT
            return FlightState.LAUNCH_DETECT

        if s == FlightState.ASCENT:
            if velocity <= 0:
                self._neg_velocity_count += 1
            else:
                self._neg_velocity_count = 0
            if self._neg_velocity_count >= APOGEE_CONFIRM_STEPS:
                return FlightState.APOGEE
            return FlightState.ASCENT

        if s == FlightState.APOGEE:
            if velocity < 0:
                return FlightState.DESCENT
            return FlightState.APOGEE

        if s == FlightState.DESCENT:
            at_ground = altitude <= LANDED_ALTITUDE_THRESHOLD
            accel_ok = LANDED_ACCEL_LOW <= accel_g <= LANDED_ACCEL_HIGH
            if at_ground and accel_ok:
                return FlightState.LANDED
            return FlightState.DESCENT

        # LANDED ve ERROR fazları terminal — değişmez
        return s

    def get_state_history(self) -> list:
        """[(time_s, FlightState)] listesini döner."""
        return list(self._history)

    def is_terminal(self) -> bool:
        """Simülasyon sona erdi mi?"""
        return self.state in (FlightState.LANDED, FlightState.ERROR)
