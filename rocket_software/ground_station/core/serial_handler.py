"""Gerçek seri port veya simülasyon modunu yöneten QThread."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from simulation.flight_generator import FlightConfig
from .packet_parser import PacketParser, TelemetryPacket
from .sim_bridge import SimBridge


class SerialHandler(QThread):
    """Paketi parse edip sinyal yayınlar. Gerçek veya simüle port destekler."""

    packet_received = pyqtSignal(TelemetryPacket)
    connection_lost = pyqtSignal(str)
    connection_ok = pyqtSignal(str)

    def __init__(self, port: str | None = None, baud: int = 115200,
                 sim_mode: bool = False,
                 sim_config: FlightConfig | None = None,
                 parent=None):
        super().__init__(parent)
        self._port = port
        self._baud = baud
        self._sim_mode = sim_mode
        self._sim_config = sim_config
        self._parser = PacketParser()
        self._running = False
        self._serial = None

    def run(self):
        self._running = True
        if self._sim_mode:
            self._run_sim()
        else:
            self._run_serial()

    def _run_sim(self):
        bridge = SimBridge(self._sim_config)
        self.connection_ok.emit("Simülasyon modu aktif")
        while self._running and bridge.is_open:
            raw = bridge.readline()
            if not raw:
                break
            line = raw.decode("ascii", errors="ignore")
            packet = self._parser.parse(line)
            if packet:
                self.packet_received.emit(packet)
            self.msleep(10)  # 10ms — 100 paket/s (gerçek zamanlı hız)
        self.connection_lost.emit("Simülasyon tamamlandı")

    def _run_serial(self):
        try:
            import serial
            ser = serial.Serial(self._port, self._baud, timeout=1)
            self._serial = ser
            self.connection_ok.emit(f"{self._port} bağlandı")
        except Exception as e:
            self.connection_lost.emit(f"Port açılamadı: {e}")
            return

        while self._running:
            try:
                if not self._serial.is_open:
                    break
                raw = self._serial.readline()
                if not raw:
                    continue
                line = raw.decode("ascii", errors="ignore")
                packet = self._parser.parse(line)
                if packet:
                    self.packet_received.emit(packet)
            except Exception as e:
                self.connection_lost.emit(str(e))
                break

        if self._serial and self._serial.is_open:
            self._serial.close()

    def stop(self):
        self._running = False
        if self._serial and self._serial.is_open:
            self._serial.close()
        self.wait(2000)

    @staticmethod
    def get_available_ports() -> list:
        """Sistemdeki seri portları listeler."""
        try:
            from serial.tools import list_ports
            return [p.device for p in list_ports.comports()]
        except ImportError:
            return []
