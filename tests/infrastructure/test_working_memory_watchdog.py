"""WorkingMemory high-water-mark watchdog tests (PHREAK P2.3).

Pure stateless scoring keeps the unified working memory near-empty. An
assert-without-retract leak would otherwise grow silently for the full TTL
window (§6). The watchdog logs a one-time WARNING when the resident fact count
crosses a configurable high-water mark. These tests pin that behavior and the
EngineConfig plumbing.
"""

import logging

import pytest

from fluxrules.engine.configuration import EngineConfig, set_config
from fluxrules.engine.infrastructure.working_memory import UnifiedWorkingMemory
from fluxrules.engine.phreak._engine import PhreakEngine


class TestWorkingMemoryWatchdog:
    def test_warns_once_above_high_water_mark(self, caplog):
        wm = UnifiedWorkingMemory(high_water_mark=3)
        with caplog.at_level(logging.WARNING):
            for i in range(3):
                wm.assert_fact({"i": i})
            assert not _watchdog_warnings(caplog)  # at the mark, not above
            wm.assert_fact({"i": 3})  # 4 > 3 -> warns
            warnings = _watchdog_warnings(caplog)
            assert len(warnings) == 1
            # Further asserts while still above the mark do NOT re-warn.
            wm.assert_fact({"i": 4})
            wm.assert_fact({"i": 5})
            assert len(_watchdog_warnings(caplog)) == 1

    def test_rearms_after_dropping_below_mark(self, caplog):
        wm = UnifiedWorkingMemory(high_water_mark=2)
        ids = []
        with caplog.at_level(logging.WARNING):
            for i in range(3):
                ids.append(wm.assert_fact({"i": i}))  # 3 > 2 -> warns once
            assert len(_watchdog_warnings(caplog)) == 1
            # Drop back under the mark; the watchdog re-arms.
            wm.retract_fact(ids[0])
            wm.retract_fact(ids[1])
            assert len(wm) == 1
            # Breach again -> a fresh warning.
            wm.assert_fact({"i": 10})
            wm.assert_fact({"i": 11})  # back above 2
            assert len(_watchdog_warnings(caplog)) == 2

    def test_disabled_when_mark_is_zero(self, caplog):
        wm = UnifiedWorkingMemory(high_water_mark=0)
        with caplog.at_level(logging.WARNING):
            for i in range(50):
                wm.assert_fact({"i": i})
            assert not _watchdog_warnings(caplog)
        assert wm.high_water_mark == 0


class TestWatchdogConfigPlumbing:
    def test_engine_config_drives_high_water_mark(self):
        original = EngineConfig()
        try:
            set_config(EngineConfig(working_memory_high_water_mark=7))
            engine = PhreakEngine()
            assert engine.working_memory.high_water_mark == 7
        finally:
            set_config(original)

    def test_engine_config_drives_node_memory_bound(self):
        original = EngineConfig()
        try:
            set_config(EngineConfig(node_memory_max_entries=512))
            engine = PhreakEngine(streaming_mode=True)
            assert engine._node_memory is not None
            assert engine._node_memory.stats["max_entries"] == 512
        finally:
            set_config(original)


def _watchdog_warnings(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING and "high-water mark" in r.getMessage()
    ]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
