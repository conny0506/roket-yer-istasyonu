"""pyqtgraph ile canlı irtifa + hız grafiği (2 panel)."""

from __future__ import annotations

from collections import deque

import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt

_MAX_POINTS = 60_000  # 100 Hz × 600 s — tüm uçuş ekranda kalır

_STATE_COLORS = {
    "IDLE":          (170, 170, 170),
    "ARMED":         (68,  102, 255),
    "LAUNCH_DETECT": (255, 153,   0),
    "ASCENT":        (0,   204,  68),
    "APOGEE":        (255,  68,  68),
    "DESCENT":       (255, 136,  68),
    "LANDED":        (136,  85,  34),
    "ERROR":         (255,   0, 255),
}


class AltitudeWidget(QWidget):
    """İrtifa (üst) + Hız (alt) canlı grafik paneli."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._times: deque = deque(maxlen=_MAX_POINTS)
        self._alts:  deque = deque(maxlen=_MAX_POINTS)
        self._vels:  deque = deque(maxlen=_MAX_POINTS)
        self._apogee_time: float | None = None
        self._setup_ui()

    def _setup_ui(self):
        pg.setConfigOption("background", "#1a1a2e")
        pg.setConfigOption("foreground", "#cccccc")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # --- İrtifa grafiği ---
        self._alt_plot = pg.PlotWidget(title="İrtifa")
        self._alt_plot.setLabel("left", "İrtifa", units="m")
        self._alt_plot.showGrid(x=True, y=True, alpha=0.3)
        self._alt_plot.setMinimumHeight(160)
        self._alt_curve = self._alt_plot.plot(
            pen=pg.mkPen(color=(0, 204, 68), width=2)
        )
        self._apogee_line = None
        layout.addWidget(self._alt_plot)

        # --- Hız grafiği ---
        self._vel_plot = pg.PlotWidget(title="Hız")
        self._vel_plot.setLabel("left", "Hız", units="m/s")
        self._vel_plot.setLabel("bottom", "Zaman", units="s")
        self._vel_plot.showGrid(x=True, y=True, alpha=0.3)
        self._vel_plot.setMinimumHeight(130)
        self._vel_curve = self._vel_plot.plot(
            pen=pg.mkPen(color=(68, 170, 255), width=2)
        )
        # Sıfır çizgisi
        self._vel_plot.addItem(
            pg.InfiniteLine(pos=0, angle=0,
                            pen=pg.mkPen(color=(100, 100, 100), width=1,
                                         style=Qt.PenStyle.DashLine))
        )
        layout.addWidget(self._vel_plot)

        # İki grafik x eksenini birbirine bağla
        self._vel_plot.setXLink(self._alt_plot)

        self.setLayout(layout)

    def update_data(self, time_s: float, altitude: float,
                    velocity: float, state: str):
        self._times.append(time_s)
        self._alts.append(altitude)
        self._vels.append(velocity)

        color = _STATE_COLORS.get(state, (255, 255, 255))
        pen = pg.mkPen(color=color, width=2)

        t = list(self._times)
        self._alt_curve.setPen(pen)
        self._alt_curve.setData(t, list(self._alts))

        # Hız eğrisi: pozitif → açık mavi, negatif → turuncu
        vel_list = list(self._vels)
        vel_color = (68, 170, 255) if (vel_list[-1] >= 0) else (255, 136, 68)
        self._vel_curve.setPen(pg.mkPen(color=vel_color, width=2))
        self._vel_curve.setData(t, vel_list)

        # Apogee işaretçisi
        if state == "APOGEE" and self._apogee_time is None:
            self._apogee_time = time_s
            for plot in (self._alt_plot, self._vel_plot):
                plot.addItem(pg.InfiniteLine(
                    pos=time_s, angle=90,
                    pen=pg.mkPen(color=(255, 68, 68), width=1,
                                 style=Qt.PenStyle.DashLine),
                    label=f"Apogee {altitude:.0f}m",
                    labelOpts={"color": (255, 68, 68), "position": 0.85}
                ))

    def reset(self):
        self._times.clear()
        self._alts.clear()
        self._vels.clear()
        self._apogee_time = None
        self._alt_curve.setData([], [])
        self._vel_curve.setData([], [])
        # Apogee çizgisini temizle
        for plot in (self._alt_plot, self._vel_plot):
            for item in list(plot.plotItem.items):
                if isinstance(item, pg.InfiniteLine) and item.angle == 90:
                    plot.removeItem(item)
