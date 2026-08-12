import asyncio
from unittest.mock import AsyncMock

import pytest

from tools.native_scanner import NativeScanner, ScanResult, ScanTarget


def test_scan_targets_converts_detector_exception_to_scan_result():
    scanner = NativeScanner()
    scanner._fetch = AsyncMock(
        side_effect=[ScanResult(url="https://ok.example", status_code=200), RuntimeError("network error")]
    )

    results = asyncio.run(
        scanner.scan_targets([ScanTarget("https://ok.example"), ScanTarget("https://bad.example")])
    )

    assert results[0].status_code == 200
    assert results[1].url == "unknown"
    assert results[1].error == "network error"


def test_scan_targets_preserves_task_cancellation():
    scanner = NativeScanner()
    scanner._fetch = AsyncMock(return_value=asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(scanner.scan_targets([ScanTarget("https://cancel.example")]))
