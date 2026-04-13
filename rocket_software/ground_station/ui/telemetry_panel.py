"""Anlık telemetri değerlerini gösteren panel."""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QGridLayout, QLabel, QFrame
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ground_station.core.packet_parser import TelemetryPacket

_STATE_COLORS = {
    "IDLE":          "#888888",
    "ARMED":         "#4466ff",
    "LAUNCH_DETECT": "#ff9900",
    "ASCENT":        "#00cc44",
    "APOGEE":        "#ff4444",
    "DESCENT":       "#ff8844",
    "LANDED":        "#885522",
    "ERROR":         "#ff00ff",
}

_BATT_GREEN  = 7.5   # V üstü
_BATT_YELLOW = 7.0   # V üstü sarı
# altı kırmızı


class TelemetryPanel(QWidget):
    """QGridLayout ile başlık/değer çiftleri gösteren telemetri paneli."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._packet_count = 0
        self._crc_errors = 0
        self._value_labels: dict[str, QLabel] = {}
        self._setup_ui()

    def _setup_ui(self):
        self.setMinimumWidth(220)
        layout = QGridLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 8, 8, 8)

        title = QLabel("TELEMETRİ")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bold = QFont()
        bold.setBold(True)
        bold.setPointSize(11)
        title.setFont(bold)
        layout.addWidget(title, 0, 0, 1, 2)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator, 1, 0, 1, 2)

        rows = [
            ("faz",     "Faz",      "---"),
            ("alt",     "İrtifa",   "--- m"),
            ("vel",     "Hız",      "--- m/s"),
            ("acc",     "İvme",     "--- g"),
            ("gps",     "GPS",      "---"),
            ("batt",    "Batarya",  "--- V"),
            ("status",  "Sistem",   "---"),
            ("time",    "Zaman",    "0.00 s"),
            ("pkts",    "Paket",    "0"),
            ("crc",     "CRC Hata", "0"),
        ]

        for i, (key, label_text, default) in enumerate(rows, start=2):
            lbl = QLabel(label_text + ":")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val = QLabel(default)
            val.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            val.setFont(QFont("Consolas", 10))
            layout.addWidget(lbl, i, 0)
            layout.addWidget(val, i, 1)
            self._value_labels[key] = val

        self.setLayout(layout)

    def update(self, packet: TelemetryPacket):
        self._packet_count += 1
        if not packet.crc_valid:
            self._crc_errors += 1

        v = self._value_labels

        # Faz — renkli badge
        color = _STATE_COLORS.get(packet.state, "#ffffff")
        v["faz"].setText(packet.state)
        v["faz"].setStyleSheet(
            f"color: {color}; font-weight: bold;"
        )

        v["alt"].setText(f"{packet.altitude:.1f} m")
        v["vel"].setText(f"{packet.velocity:+.2f} m/s")
        v["acc"].setText(f"{packet.accel:.2f} g")
        v["gps"].setText(f"{packet.lat:.4f}, {packet.lon:.4f}")
        v["time"].setText(f"{packet.timestamp_ms / 1000:.2f} s")
        v["pkts"].setText(str(self._packet_count))
        v["crc"].setText(
            str(self._crc_errors) if self._crc_errors == 0
            else f'<span style="color:red">{self._crc_errors}</span>'
        )
        v["crc"].setTextFormat(Qt.TextFormat.RichText)

        # Batarya rengi
        bv = packet.battery
        if bv >= _BATT_GREEN:
            batt_color = "color: #00cc44;"
        elif bv >= _BATT_YELLOW:
            batt_color = "color: #ffaa00;"
        else:
            batt_color = "color: red; font-weight: bold;"
        v["batt"].setText(f"{bv:.2f} V")
        v["batt"].setStyleSheet(batt_color)

        # Sistem durumu
        status_colors = {"OK": "#00cc44", "WARN": "#ffaa00", "ERR": "red"}
        sc = status_colors.get(packet.status, "#ffffff")
        v["status"].setText(packet.status)
        v["status"].setStyleSheet(f"color: {sc}; font-weight: bold;")

        # ERROR fazında panel kenarlığı
        if packet.state == "ERROR":
            self.setStyleSheet("QWidget { border: 2px solid red; }")
        else:
            self.setStyleSheet("")

    def reset(self):
        self._packet_count = 0
        self._crc_errors = 0
        for key, lbl in self._value_labels.items():
            lbl.setText("---")
            lbl.setStyleSheet("")
        self.setStyleSheet("")
