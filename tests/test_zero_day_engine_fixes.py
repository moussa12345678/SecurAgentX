import asyncio
from unittest.mock import AsyncMock

import pytest

from tools.zero_day_heuristics import ScanConfig, ZeroDayEngine


_DETECTOR_METHODS = (
    "_run_prototype",
    "_run_mass_assignment",
    "_run_deserialization",
    "_run_smuggling",
    "_run_race",
    "_run_ssti",
    "_run_graphql",
    "_run_anomaly",
)


def _engine_with_stubbed_detectors() -> ZeroDayEngine:
    engine = ZeroDayEngine(ScanConfig(enable_jwt=False))
    for method_name in _DETECTOR_METHODS:
        setattr(engine, method_name, AsyncMock(return_value=[]))
    return engine


def test_scan_skips_detector_base_exception_results():
    engine = _engine_with_stubbed_detectors()
    engine._run_prototype = AsyncMock(return_value=RuntimeError("detector failed"))

    findings = asyncio.run(engine.scan("https://example.com"))

    assert findings == []


def test_scan_preserves_cancellation_from_detector_results():
    engine = _engine_with_stubbed_detectors()
    engine._run_prototype = AsyncMock(return_value=asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(engine.scan("https://example.com"))
