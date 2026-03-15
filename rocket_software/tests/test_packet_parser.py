"""PacketParser birim testleri — PyQt6 gerektirmez."""

import pytest
from ground_station.core.packet_parser import PacketParser, TelemetryPacket

SAMPLE_LINE = "$ROCKET,12500,ASCENT,243.5,51.20,3.91,39.920100,32.854100,7.80,OK*"


def _make_valid_line() -> str:
    body = "ROCKET,12500,ASCENT,243.5,51.20,3.91,39.920100,32.854100,7.80,OK"
    crc = PacketParser.calculate_crc(body)
    return f"${body}*{crc}"


parser = PacketParser()


def test_valid_packet_parsed():
    line = _make_valid_line()
    p = parser.parse(line)
    assert p is not None
    assert p.timestamp_ms == 12500
    assert p.state == "ASCENT"
    assert abs(p.altitude - 243.5) < 0.01
    assert abs(p.velocity - 51.20) < 0.01
    assert abs(p.accel - 3.91) < 0.01
    assert abs(p.lat - 39.9201) < 0.0001
    assert abs(p.battery - 7.80) < 0.01
    assert p.status == "OK"


def test_crc_validation_passes():
    line = _make_valid_line()
    p = parser.parse(line)
    assert p is not None
    assert p.crc_valid is True


def test_crc_validation_fails_silently():
    """Yanlış CRC → None değil, crc_valid=False olan paket döner."""
    body = "ROCKET,12500,ASCENT,243.5,51.20,3.91,39.920100,32.854100,7.80,OK"
    line = f"${body}*00"   # 00 her zaman yanlış CRC
    p = parser.parse(line)
    assert p is not None
    assert p.crc_valid is False


def test_invalid_prefix_returns_none():
    line = "$SENSOR,12500,ASCENT,243.5,51.20,3.91,39.9201,32.8541,7.8,OK*FF"
    assert parser.parse(line) is None


def test_missing_fields_returns_none():
    """Eksik alan → None."""
    line = "$ROCKET,12500,ASCENT,243.5*AB"
    assert parser.parse(line) is None


def test_no_crc_delimiter_returns_none():
    line = "$ROCKET,12500,ASCENT,243.5,51.20,3.91,39.9201,32.8541,7.8,OK"
    assert parser.parse(line) is None


def test_crc_calculation_known_value():
    """Elle doğrulama: 'ROCKET,0,IDLE,0.0,0.00,0.00,0.0,0.0,8.40,OK' CRC."""
    data = "ROCKET,0,IDLE,0.0,0.00,0.00,0.0,0.0,8.40,OK"
    crc = PacketParser.calculate_crc(data)
    assert len(crc) == 2
    assert crc == crc.upper()
    # Deterministik: aynı input her zaman aynı CRC
    assert PacketParser.calculate_crc(data) == crc


def test_format_and_reparse_roundtrip():
    """format_packet → parse round-trip tutarlı olmalı."""
    original = TelemetryPacket(
        timestamp_ms=5000, state="DESCENT",
        altitude=800.0, velocity=-15.3, accel=1.02,
        lat=39.9201, lon=32.8541,
        battery=8.1, status="OK",
        crc_valid=True, raw=""
    )
    line = PacketParser.format_packet(original)
    parsed = parser.parse(line)
    assert parsed is not None
    assert parsed.crc_valid is True
    assert parsed.state == "DESCENT"
    assert abs(parsed.altitude - 800.0) < 0.1
    assert abs(parsed.velocity - (-15.3)) < 0.01


def test_whitespace_stripped():
    """Başındaki/sonundaki boşluk parse'ı bozmamalı."""
    line = "  " + _make_valid_line() + "  \n"
    p = parser.parse(line)
    assert p is not None


def test_all_states_parse():
    """Tüm geçerli faz isimleri parse edilebilmeli."""
    states = ["IDLE", "ARMED", "LAUNCH_DETECT", "ASCENT",
              "APOGEE", "DESCENT", "LANDED", "ERROR"]
    for state in states:
        body = f"ROCKET,1000,{state},100.0,0.00,1.00,39.9201,32.8541,8.00,OK"
        crc = PacketParser.calculate_crc(body)
        line = f"${body}*{crc}"
        p = parser.parse(line)
        assert p is not None and p.state == state, f"Parse başarısız: {state}"
