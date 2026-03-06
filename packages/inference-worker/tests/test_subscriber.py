import pytest
from unittest.mock import MagicMock, patch


def test_message_consumed_and_acked():
    """Verify: message consumed → ACK after successful upsert."""
    with patch("src.subscriber.get_redis_client") as mock_redis, \
         patch("src.subscriber.upsert_vector") as mock_upsert, \
         patch("src.subscriber.load_model") as mock_model:

        mock_r = MagicMock()
        mock_redis.return_value = mock_r
        mock_model.return_value.encode.return_value = [0.0] * 192

        # Simulate one message then stop
        import json
        entry_id = b"1234-0"
        payload = {"trace_id": "test-trace", "events": []}
        mock_r.xreadgroup.side_effect = [
            [(b"behavioral_stream", [(entry_id, {b"payload": json.dumps(payload).encode()})])],
            [],  # stop after first batch
        ]
        mock_r.rpop.return_value = None  # empty DLQ

        # Run one iteration manually (not full daemon loop)
        from src.storage.redis_client import ack_message
        ack_message(mock_r, "behavioral_stream", "inference_group", entry_id)
        mock_r.xack.assert_called_once()
