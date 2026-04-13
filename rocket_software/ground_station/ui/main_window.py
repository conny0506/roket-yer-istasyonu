"""Ana PyQt6 penceresi — tüm bileşenleri orkestre eder."""

from __future__ import annotations

import threading
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QToolBar, QStatusBar, QMessageBox,
    QInputDialog, QLabel, QSplitter,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from ground_station.core.packet_parser import TelemetryPacket
from ground_station.core.serial_handler import SerialHandler
from ground_station.core.data_recorder import DataRecorder
from ground_station.ui.telemetry_panel import TelemetryPanel
from ground_station.ui.altitude_widget import AltitudeWidget
from ground_station.ui.map_widget import MapWidget
from simulation.constants import GPS_LAT0, GPS_LON0

_LOGS_DIR = Path(__file__).parent.parent.parent / "data" / "logs"
_BATTERY_WARN_V = 7.0


def _beep(freq: int, duration: int):
    """Arka planda bip sesi çal (Windows)."""
    def _play():
        try:
            import winsound
            winsound.Beep(freq, duration)
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()


def _beep_pattern(pattern: list):
    """(freq, duration_ms, pause_ms) listesi olarak bip dizisi çal."""
    def _play():
        try:
            import winsound, time
            for freq, dur, pause in pattern:
                winsound.Beep(freq, dur)
                if pause:
                    time.sleep(pause / 1000)
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Roket Yer İstasyonu")
        self.resize(1200, 720)

        self._handler: SerialHandler | None = None
        self._recorder: DataRecorder | None = None
        self._recording = False
        self._packet_count = 0
        self._battery_warned = False
        self._apogee_signaled = False
        self._landed_signaled = False
        self._last_state = ""

        # Fırlatma noktası sabit (Ankara). Hedef haritadan seçilir.
        self._launch_lat = GPS_LAT0
        self._launch_lon = GPS_LON0
        self._target_lat: float | None = None
        self._target_lon: float | None = None

        self._packet_timer = QTimer(self)
        self._packet_timer.timeout.connect(self._update_packet_rate)
        self._packets_last_sec = 0

        self._build_ui()
        self._build_toolbar()
        self._build_statusbar()

        # Fırlatma marker'ı (Ankara) baştan görünsün
        self._map.set_launch_marker(self._launch_lat, self._launch_lon)

    # ------------------------------------------------------------------
    # UI kurulum
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        outer = QHBoxLayout(central)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        # Sol: telemetri paneli
        self._telemetry = TelemetryPanel()
        outer.addWidget(self._telemetry)

        # Sağ: grafik üstte, harita altta
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        self._altitude = AltitudeWidget()
        self._map = MapWidget()
        self._map.launch_point_selected.connect(self._on_launch_point_selected)

        right_splitter.addWidget(self._altitude)
        right_splitter.addWidget(self._map)
        right_splitter.setSizes([380, 300])

        outer.addWidget(right_splitter, stretch=1)

    def _build_toolbar(self):
        tb = QToolBar("Kontroller")
        tb.setMovable(False)
        self.addToolBar(tb)

        self._btn_sim = QPushButton("▶  Simülasyon Başlat")
        self._btn_sim.clicked.connect(self._start_simulation)
        tb.addWidget(self._btn_sim)

        self._btn_serial = QPushButton("🔌  Gerçek Port")
        self._btn_serial.clicked.connect(self._connect_serial)
        tb.addWidget(self._btn_serial)

        self._btn_stop = QPushButton("⏹  Durdur")
        self._btn_stop.clicked.connect(self._stop)
        self._btn_stop.setEnabled(False)
        tb.addWidget(self._btn_stop)

        tb.addSeparator()

        self._btn_record = QPushButton("⏺  Kayıt Başlat")
        self._btn_record.setCheckable(True)
        self._btn_record.clicked.connect(self._toggle_recording)
        tb.addWidget(self._btn_record)

        self._btn_analyze = QPushButton("📊  Analiz Et")
        self._btn_analyze.clicked.connect(self._run_analysis)
        self._btn_analyze.setEnabled(False)
        tb.addWidget(self._btn_analyze)

        tb.addSeparator()

        self._lbl_launch = QLabel("  🎯 Hedef: seçilmedi (dikey atış)")
        f = QFont("Consolas", 9)
        self._lbl_launch.setFont(f)
        self._lbl_launch.setToolTip("Haritaya tıklayarak hedef seç — roket Ankara'dan oraya uçar")
        tb.addWidget(self._lbl_launch)

    def _build_statusbar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._lbl_conn = QLabel("Bağlı değil")
        self._lbl_rate = QLabel("0 pkt/s")
        self._lbl_rec  = QLabel("")
        sb.addPermanentWidget(self._lbl_conn)
        sb.addPermanentWidget(self._lbl_rate)
        sb.addPermanentWidget(self._lbl_rec)

    # ------------------------------------------------------------------
    # Kontrol aksiyonları
    # ------------------------------------------------------------------

    def _start_simulation(self):
        self._reset_ui()
        from simulation.flight_generator import FlightConfig
        config = FlightConfig(
            launch_lat=self._launch_lat,
            launch_lon=self._launch_lon,
            target_lat=self._target_lat,
            target_lon=self._target_lon,
        )
        config.launch_site_altitude = 1000.0
        self._handler = SerialHandler(sim_mode=True, sim_config=config)
        self._connect_handler()
        self._handler.start()
        self._set_connected_state(True)
        self._packet_timer.start(1000)
        # Fırlatma + (varsa) hedef marker'larını göster
        self._map.set_launch_marker(self._launch_lat, self._launch_lon)
        if self._target_lat is not None:
            self._map.set_target_marker(self._target_lat, self._target_lon)
            self._map.fly_to_bounds(
                self._launch_lat, self._launch_lon,
                self._target_lat, self._target_lon,
            )
        else:
            self._map.fly_to(self._launch_lat, self._launch_lon)

    def _connect_serial(self):
        ports = SerialHandler.get_available_ports()
        if not ports:
            QMessageBox.warning(self, "Port Yok", "Hiçbir seri port bulunamadı.")
            return
        port, ok = QInputDialog.getItem(
            self, "Port Seç", "Seri port:", ports, 0, False
        )
        if not ok:
            return
        self._reset_ui()
        self._handler = SerialHandler(port=port, sim_mode=False)
        self._connect_handler()
        self._handler.start()
        self._set_connected_state(True)
        self._packet_timer.start(1000)

    def _stop(self):
        if self._handler:
            self._handler.stop()
            self._handler = None
        if self._recorder:
            self._recorder.close()
        self._set_connected_state(False)
        self._packet_timer.stop()
        self._btn_analyze.setEnabled(self._packet_count > 0)

    def _toggle_recording(self, checked: bool):
        if checked:
            _LOGS_DIR.mkdir(parents=True, exist_ok=True)
            self._recorder = DataRecorder(_LOGS_DIR)
            self._recording = True
            self._btn_record.setText("⏹  Kaydı Durdur")
            self._lbl_rec.setText(f"REC ● {self._recorder.get_path().name}")
        else:
            if self._recorder:
                self._recorder.close()
                self._recorder = None
            self._recording = False
            self._lbl_rec.setText("")
            self._btn_record.setText("⏺  Kayıt Başlat")

    def _run_analysis(self, auto=False):
        csv_path = None
        if self._recorder:
            csv_path = self._recorder.get_path()
        else:
            logs = sorted(_LOGS_DIR.glob("flight_*.csv")) if _LOGS_DIR.exists() else []
            if logs:
                csv_path = logs[-1]

        if not csv_path or not csv_path.exists():
            if not auto:
                QMessageBox.information(self, "Analiz", "Kayıtlı log bulunamadı.")
            return

        try:
            from analysis.log_analyzer import FlightLogAnalyzer
            from analysis.report_generator import FlightReport
            a = FlightLogAnalyzer(csv_path)
            text = FlightReport(a).to_text()
            dlg = QMessageBox(self)
            dlg.setWindowTitle("Uçuş Analizi")
            mono = QFont("Consolas", 9)
            dlg.setFont(mono)
            dlg.setText(f"<pre>{text}</pre>")
            dlg.exec()
        except Exception as e:
            if not auto:
                QMessageBox.critical(self, "Analiz Hatası", str(e))

    # ------------------------------------------------------------------
    # Sinyal bağlantıları
    # ------------------------------------------------------------------

    def _connect_handler(self):
        self._handler.packet_received.connect(self._on_packet)
        self._handler.connection_lost.connect(self._on_connection_lost)
        self._handler.connection_ok.connect(self._on_connection_ok)

    def _on_packet(self, packet: TelemetryPacket):
        self._packet_count += 1
        self._packets_last_sec += 1

        t_s = packet.timestamp_ms / 1000.0
        self._telemetry.update(packet)
        self._altitude.update_data(t_s, packet.altitude,
                                   packet.velocity, packet.state)
        self._map.update_position(packet.lat, packet.lon, packet.altitude)
        self._map.set_state(packet.state)

        # Apogee 3D işaretçisi
        if packet.state == "APOGEE" and not self._apogee_signaled:
            self._apogee_signaled = True
            self._map.mark_apogee(packet.lat, packet.lon, packet.altitude)

        if self._recording and self._recorder:
            self._recorder.record(packet)

        self._check_warnings(packet)
        self._last_state = packet.state

    def _on_connection_lost(self, msg: str):
        self._lbl_conn.setText(msg)
        self._set_connected_state(False)
        self._btn_analyze.setEnabled(self._packet_count > 0)
        # Uçuş tamamlandıysa otomatik rapor
        if self._packet_count > 50:
            QTimer.singleShot(800, lambda: self._run_analysis(auto=True))

    def _on_connection_ok(self, msg: str):
        self._lbl_conn.setText(msg)

    def _on_launch_point_selected(self, lat: float, lon: float):
        """Haritadan **hedef** seçildi (fırlatma sabit Ankara)."""
        self._target_lat = lat
        self._target_lon = lon
        self._lbl_launch.setText(f"  🎯 Hedef: {lat:.4f}, {lon:.4f}")
        # Haritada hem fırlatma hem hedef marker'ı göster
        self._map.set_launch_marker(self._launch_lat, self._launch_lon)
        self._map.set_target_marker(lat, lon)
        self.statusBar().showMessage(
            f"Hedef seçildi: {lat:.4f}, {lon:.4f}", 3000
        )

    # ------------------------------------------------------------------
    # Uyarı sistemi + ses
    # ------------------------------------------------------------------

    def _check_warnings(self, packet: TelemetryPacket):
        state = packet.state

        # Fırlatma sesi
        if self._last_state in ("ARMED", "LAUNCH_DETECT") and state == "ASCENT":
            _beep_pattern([(800, 80, 50), (1000, 80, 50), (1200, 150, 0)])

        # Apogee sesi
        if state == "APOGEE" and self._last_state != "APOGEE":
            _beep_pattern([(1500, 200, 80), (1500, 200, 0)])

        # İniş sesi
        if state == "LANDED" and not self._landed_signaled:
            self._landed_signaled = True
            _beep_pattern([
                (600, 150, 80), (800, 150, 80), (1000, 300, 0)
            ])

        # Batarya düşük
        if not self._battery_warned and packet.battery < _BATTERY_WARN_V:
            self._battery_warned = True
            _beep_pattern([(400, 200, 100)] * 3)
            self.statusBar().showMessage(
                f"⚠ BATARYA DÜŞÜK: {packet.battery:.2f}V", 6000
            )

        # CRC hatası
        if not packet.crc_valid:
            _beep(300, 60)

        # Sistem hatası
        if packet.status == "ERR" and self._last_state != "ERROR":
            _beep_pattern([(300, 300, 100), (300, 300, 0)])
            self.statusBar().showMessage(
                f"🚨 SİSTEM HATASI @ t={packet.timestamp_ms/1000:.1f}s", 4000
            )

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------

    def _update_packet_rate(self):
        self._lbl_rate.setText(f"{self._packets_last_sec} pkt/s")
        self._packets_last_sec = 0

    def _set_connected_state(self, connected: bool):
        self._btn_sim.setEnabled(not connected)
        self._btn_serial.setEnabled(not connected)
        self._btn_stop.setEnabled(connected)

    def _reset_ui(self):
        self._packet_count = 0
        self._battery_warned = False
        self._apogee_signaled = False
        self._landed_signaled = False
        self._last_state = ""
        self._telemetry.reset()
        self._altitude.reset()
        self._map.reset()

    def closeEvent(self, event):
        self._stop()
        super().closeEvent(event)
