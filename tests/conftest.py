import os

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "perf: realtime throughput check; skipped unless HIVESHOT_PERF=1")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("HIVESHOT_LIVE") == "1":
        return
    skip = pytest.mark.skip(reason="live test; set HIVESHOT_LIVE=1 to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
