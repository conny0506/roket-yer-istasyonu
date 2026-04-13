"""QWebEngineView tabanlı CesiumJS 3D harita widget'ı."""

from __future__ import annotations

import threading
import http.server
import socketserver
import socket
from pathlib import Path

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import QUrl, Qt, QObject, pyqtSlot, pyqtSignal

_ASSETS_DIR = Path(__file__).parent.parent / "assets"


def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_asset_server(directory: Path, port: int):
    """assets/ klasörünü localhost üzerinden servis eden HTTP sunucu."""
    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)
        def log_message(self, *a):
            pass

    class _Server(socketserver.TCPServer):
        allow_reuse_address = True

    httpd = _Server(("127.0.0.1", port), _Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


class _MapBridge(QObject):
    """JS → Python köprüsü: fırlatma noktası seçimi."""
    launch_point_selected = pyqtSignal(float, float)

    @pyqtSlot(float, float)
    def setLaunchPoint(self, lat: float, lon: float):
        self.launch_point_selected.emit(lat, lon)


class MapWidget(QWidget):
    """CesiumJS 3D harita. Fırlatma noktası seçimi için sinyal yayınlar."""

    launch_point_selected = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ready = False
        self._pending: list = []
        self._apogee_marked = False
        self._http_server = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings
            from PyQt6.QtWebChannel import QWebChannel

            # Localhost HTTP sunucusu başlat → CDN erişimi açılır
            port = _find_free_port()
            self._http_server = _start_asset_server(_ASSETS_DIR, port)
            self._port = port

            self._view = QWebEngineView()
            self._view.setMinimumHeight(220)

            settings = self._view.settings()
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.WebGLEnabled, True
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True
            )

            # QWebChannel kurulumu (JS → Python)
            self._bridge = _MapBridge()
            self._bridge.launch_point_selected.connect(self.launch_point_selected)
            channel = QWebChannel(self._view.page())
            channel.registerObject("pybridge", self._bridge)
            self._view.page().setWebChannel(channel)

            # file:// yerine http://localhost kullan
            url = QUrl(f"http://127.0.0.1:{port}/map_template.html")
            self._view.load(url)
            self._view.loadFinished.connect(self._on_load_finished)
            layout.addWidget(self._view)
            self._web_available = True

        except Exception as e:
            print(f"[MapWidget] WebEngine hatası: {type(e).__name__}: {e}")
            lbl = QLabel("3D Harita yüklenemedi.\npip install PyQt6-WebEngine")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #f88; font-size: 12px;")
            layout.addWidget(lbl)
            self._web_available = False

        self.setLayout(layout)

    def _on_load_finished(self, ok: bool):
        self._ready = ok
        if ok:
            for args in self._pending:
                self._run_js(*args)
            self._pending.clear()

    def _run_js(self, js: str):
        if self._ready:
            self._view.page().runJavaScript(js)
        else:
            self._pending.append((js,))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_position(self, lat: float, lon: float, altitude: float = 1000.0):
        self._run_js(f"window.updateMarker({lat},{lon},{altitude});")
        self._run_js(f"window.addTrailPoint({lat},{lon},{altitude});")

    def set_state(self, state: str):
        self._run_js(f'window.setFlightState("{state}");')

    def mark_apogee(self, lat: float, lon: float, altitude: float):
        if not self._apogee_marked:
            self._apogee_marked = True
            self._run_js(f"window.setApogee({lat},{lon},{altitude});")

    def fly_to(self, lat: float, lon: float):
        self._run_js(f"window.flyToLaunch({lat},{lon});")

    def set_launch_marker(self, lat: float, lon: float):
        self._run_js(f"window.setLaunchMarker({lat},{lon});")

    def set_target_marker(self, lat: float, lon: float):
        self._run_js(f"window.setTargetMarker({lat},{lon});")

    def fly_to_bounds(self, lat1: float, lon1: float, lat2: float, lon2: float):
        self._run_js(f"window.flyToBounds({lat1},{lon1},{lat2},{lon2});")

    def reset(self):
        self._apogee_marked = False
        self._pending.clear()
        if self._web_available and self._ready:
            self._run_js("window.resetMap();")
