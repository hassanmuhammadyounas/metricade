import time
import pytest
from unittest.mock import MagicMock, patch
from src.health.heartbeat import run_heartbeat
from src.constants import HEARTBEAT_KEY, HEARTBEAT_INTERVAL_S


def test_redis_key_written_within_interval():
    """Heartbeat must write to Redis within HEARTBEAT_INTERVAL_S seconds."""
    written_values = []

    mock_r = MagicMock()
    mock_r.set.side_effect = lambda key, val, ex=None: written_values.append((key, val))

    with patch("src.health.heartbeat.get_redis_client", return_value=mock_r), \
         patch("src.health.heartbeat.time.sleep", side_effect=StopIteration):
        try:
            run_heartbeat()
        except StopIteration:
            pass

    assert len(written_values) == 1
    key, val = written_values[0]
    assert key == HEARTBEAT_KEY
    # Value should be a recent timestamp (within 5 seconds of now)
    ts_ms = int(val)
    assert abs(ts_ms - int(time.time() * 1000)) < 5000
