"""EPA PM2.5→AQI conversion, including the breakpoint-gap cases that previously
returned the 500 fallback."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "crawlers"))
from fetch_air_quality import pm25_to_aqi  # noqa: E402


def test_band_midpoints():
    assert pm25_to_aqi(10.0) == 42
    assert pm25_to_aqi(20.0) == 68
    assert pm25_to_aqi(60.0) == 153


def test_breakpoint_gap_values_do_not_return_500():
    # 12.05 truncates to 12.0 (good band), NOT the 500 fallback
    assert pm25_to_aqi(12.05) == 50
    # 35.45 truncates to 35.4 (top of moderate band)
    assert pm25_to_aqi(35.45) == 100


def test_zero_and_negative():
    assert pm25_to_aqi(0.0) == 0
    assert pm25_to_aqi(-1.0) == 0


def test_high_value_caps_at_500():
    assert pm25_to_aqi(500.0) == 500
