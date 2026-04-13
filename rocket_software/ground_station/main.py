"""Roket Yer İstasyonu giriş noktası."""

import sys
from pathlib import Path

# rocket_software/ kökünü path'e ekle (doğrudan çalıştırma için)
sys.path.insert(0, str(Path(__file__).parent.parent))

# WebEngine QApplication'dan ÖNCE import edilmeli (Qt zorunluluğu)
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView as _  # noqa: F401
except ImportError:
    pass

from PyQt6.QtWidgets import QApplication
from ground_station.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Roket Yer İstasyonu")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
