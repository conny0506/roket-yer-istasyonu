"""Uçuş analizi sonuçlarını metin ve Markdown raporuna dönüştürür."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from .log_analyzer import FlightLogAnalyzer
from .plotter import plot_flight


class FlightReport:
    """Analiz sonuçlarını okunabilir formata döker."""

    def __init__(self, analyzer: FlightLogAnalyzer):
        self._a = analyzer
        self._summary = analyzer.summary()
        self._timeline = analyzer.phase_timeline()
        self._anomalies = analyzer.detect_anomalies()

    # ------------------------------------------------------------------
    # Terminal çıktısı
    # ------------------------------------------------------------------

    def to_text(self) -> str:
        s = self._summary
        lines = [
            "=" * 52,
            "  ROKET UÇUŞ ANALİZ RAPORU",
            f"  Kaynak : {self._a.csv_path.name}",
            f"  Tarih  : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "=" * 52,
            "",
            "[ GENEL ÖZET ]",
            f"  Apogee          : {s['apogee_altitude_m']} m  "
            f"(t = {s['apogee_time_s']} s)",
            f"  Maks. hız       : {s['max_velocity_ms']} m/s",
            f"  Maks. ivme      : {s['max_accel_g']} g",
            f"  İniş hızı       : {s['landing_velocity_ms']} m/s",
            f"  Uçuş süresi     : {s['flight_duration_s']} s",
            f"  Son faz         : {s['final_state']}",
            f"  Anomali sayısı  : {s['anomaly_count']}",
            "",
            "[ FAZ ZAMAN ÇİZELGESİ ]",
        ]

        for _, row in self._timeline.iterrows():
            lines.append(
                f"  {row['phase']:<16} "
                f"{row['start_ms']/1000:>6.2f}s -> "
                f"{row['end_ms']/1000:>6.2f}s  "
                f"({row['duration_s']}s)"
            )

        if self._anomalies:
            lines += ["", "[ ANOMALİLER ]"]
            for a in self._anomalies:
                lines.append(
                    f"  [{a['severity'].upper():^8}] "
                    f"t={a['time_ms']/1000:.2f}s  "
                    f"{a['type']}  →  {a['value']}"
                )
        else:
            lines += ["", "[ ANOMALİ ] Tespit edilmedi."]

        lines += ["", "=" * 52]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Markdown raporu
    # ------------------------------------------------------------------

    def to_markdown(self, save_path: str | Path | None = None) -> str:
        s = self._summary
        src = self._a.csv_path.name
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        lines = [
            f"# Uçuş Analiz Raporu — {src}",
            f"*Oluşturulma: {now}*",
            "",
            "## Özet",
            "",
            "| Parametre | Değer |",
            "|---|---|",
            f"| Apogee İrtifası | **{s['apogee_altitude_m']} m** |",
            f"| Apogee Zamanı | {s['apogee_time_s']} s |",
            f"| Maksimum Hız | {s['max_velocity_ms']} m/s |",
            f"| Maksimum İvme | {s['max_accel_g']} g |",
            f"| İniş Hızı | {s['landing_velocity_ms']} m/s |",
            f"| Toplam Uçuş Süresi | {s['flight_duration_s']} s |",
            f"| Son Faz | `{s['final_state']}` |",
            f"| Anomali Sayısı | {s['anomaly_count']} |",
            "",
            "## Faz Zaman Çizelgesi",
            "",
            "| Faz | Başlangıç (s) | Bitiş (s) | Süre (s) |",
            "|---|---|---|---|",
        ]

        for _, row in self._timeline.iterrows():
            lines.append(
                f"| `{row['phase']}` "
                f"| {row['start_ms']/1000:.2f} "
                f"| {row['end_ms']/1000:.2f} "
                f"| {row['duration_s']} |"
            )

        lines += [""]

        if self._anomalies:
            lines += [
                "## Anomaliler",
                "",
                "| Zaman (s) | Tür | Değer | Seviye |",
                "|---|---|---|---|",
            ]
            for a in self._anomalies:
                lines.append(
                    f"| {a['time_ms']/1000:.2f} "
                    f"| `{a['type']}` "
                    f"| {a['value']} "
                    f"| **{a['severity']}** |"
                )
            lines.append("")
        else:
            lines += ["## Anomaliler", "", "_Tespit edilmedi._", ""]

        md = "\n".join(lines)

        if save_path:
            Path(save_path).write_text(md, encoding="utf-8")

        return md

    # ------------------------------------------------------------------
    # Grafik kaydet
    # ------------------------------------------------------------------

    def save_plot(self, output_dir: str | Path) -> Path:
        out = Path(output_dir) / (self._a.csv_path.stem + "_plot.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        plot_flight(self._a.df, save_path=out, show=False)
        return out

    # ------------------------------------------------------------------
    # Hepsini bir arada üret
    # ------------------------------------------------------------------

    def generate(self, output_dir: str | Path | None = None) -> dict:
        if output_dir is None:
            output_dir = self._a.csv_path.parent.parent / "reports"
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        report_path = out / (self._a.csv_path.stem + "_report.md")
        self.to_markdown(save_path=report_path)

        plot_path = self.save_plot(out)

        return {
            "report_path": report_path,
            "plot_path":   plot_path,
            "summary":     self._summary,
        }


# ------------------------------------------------------------------
# Tek satır API
# ------------------------------------------------------------------

def generate_report(csv_path: str | Path,
                    output_dir: str | Path | None = None) -> dict:
    """CSV'den okuyup rapor + grafik üretir. Sonuç dict döner."""
    analyzer = FlightLogAnalyzer(csv_path)
    report = FlightReport(analyzer)
    return report.generate(output_dir)
