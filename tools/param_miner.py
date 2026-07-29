"""
tools/param_miner.py — Hidden Parameter Discovery
- Baseline fingerprinting (status + length)
- Concurrent parameter probing
- Reflection detection in response body
"""

from __future__ import annotations

import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

import requests

logger = logging.getLogger("securagentx.param_miner")

# Issue 32 (P8-C): TLS verification is ON by default. Set
# SECURAGENTX_INSECURE=1|true|yes to opt into verify=False for hostile
# targets (self-signed certs, pentest labs). See verify=not INSECURE calls.
INSECURE = os.environ.get("SECURAGENTX_INSECURE", "").lower() in ("1", "true", "yes")

COMMON_PARAMS: List[str] = [
    "id",
    "page",
    "limit",
    "offset",
    "debug",
    "test",
    "admin",
    "user",
    "token",
    "key",
    "api_key",
    "secret",
    "auth",
    "access",
    "redirect",
    "url",
    "next",
    "return",
    "callback",
    "ref",
    "source",
    "v",
    "version",
    "format",
    "output",
    "type",
    "action",
    "method",
    "lang",
    "locale",
    "sort",
    "order",
    "filter",
    "search",
    "q",
    "query",
    "file",
    "path",
    "include",
    "template",
    "view",
    "layout",
    "theme",
]

_TIMEOUT = 8
_MAX_WORKERS = 15


def mine_parameters(
    url: str,
    extra_params: List[str] | None = None,
) -> List[Dict]:
    """
    Discover hidden/undocumented parameters by probing with a unique canary value.
    Returns list of found params with evidence.
    """
    params = COMMON_PARAMS + (extra_params or [])
    canary = f"securagentx_{uuid.uuid4().hex[:8]}"

    session = requests.Session()
    session.headers["User-Agent"] = "SecurAgentX-Security-Scanner/2.0"

    # Baseline
    try:
        base = session.get(url, timeout=_TIMEOUT, verify=not INSECURE)
        baseline_status = base.status_code
        baseline_len = len(base.content)
    except Exception as e:
        logger.error(f"Baseline request failed for {url}: {e}")
        return []

    found: List[Dict] = []

    def probe(param: str) -> Dict | None:
        test_url = f"{url}{'&' if '?' in url else '?'}{param}={canary}"
        try:
            r = session.get(test_url, timeout=_TIMEOUT, verify=not INSECURE)
            length_delta = abs(len(r.content) - baseline_len)
            reflected = canary in r.text

            if r.status_code != baseline_status or length_delta > 50 or reflected:
                return {
                    "param": param,
                    "url": test_url,
                    "status": r.status_code,
                    "length_delta": length_delta,
                    "reflected": reflected,
                    "base_status": baseline_status,
                }
        except Exception as e:
            logger.debug("Suppressed Exception: %s", e)
        return None

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(probe, p): p for p in params}
        for future in as_completed(futures):
            result = future.result()
            if result:
                found.append(result)
                logger.info(f"Parameter found: {result['param']} on {url}")

    session.close()
    return sorted(found, key=lambda x: x["param"])


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        print(json.dumps(mine_parameters(sys.argv[1]), indent=2))
