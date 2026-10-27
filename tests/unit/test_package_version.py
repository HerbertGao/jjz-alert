"""运行时版本号只读 jjz_alert.__version__。"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def test_package_version_is_semver():
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from jjz_alert import __version__
    from release_version import parse_version

    parse_version(__version__)


def test_home_assistant_device_reports_package_version():
    from jjz_alert import __version__
    from jjz_alert.service.homeassistant.ha_device import HAPlateDevice

    device = HAPlateDevice(plate_number="京A12345", display_name="测试车")
    assert device.get_device_info().sw_version == __version__


def test_mqtt_discovery_uses_package_version():
    from jjz_alert import __version__

    source = (
        ROOT / "jjz_alert" / "service" / "homeassistant" / "ha_mqtt.py"
    ).read_text(encoding="utf-8")
    assert '"sw_version": "2.0"' not in source
    assert '"sw_version": __version__' in source


def test_rest_api_uses_package_version():
    from jjz_alert import __version__
    import rest_api

    assert rest_api.app.version == __version__
    source = (ROOT / "rest_api.py").read_text(encoding="utf-8")
    assert '"2.0.0"' not in source
    assert source.count("__version__") >= 3
