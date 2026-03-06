import pytest
from unittest.mock import MagicMock, patch
from src.storage.vector_client import upsert_vector
from src.constants import VECTOR_DIMS


def test_upsert_calls_index_with_correct_args():
    mock_index = MagicMock()
    mock_index.fetch.return_value = [MagicMock()]  # non-None spot-check result

    with patch("src.storage.vector_client._get_index", return_value=mock_index), \
         patch("src.storage.vector_client.random.random", return_value=0.0):  # force spot-check
        upsert_vector("test-id", [0.0] * VECTOR_DIMS, {"trace_id": "test-id"})

    mock_index.upsert.assert_called_once()
    args = mock_index.upsert.call_args[1]["vectors"]
    assert args[0][0] == "test-id"
    assert len(args[0][1]) == VECTOR_DIMS


def test_spot_check_fetch_returns_non_none():
    mock_index = MagicMock()
    mock_index.fetch.return_value = [MagicMock(id="test-id")]

    with patch("src.storage.vector_client._get_index", return_value=mock_index), \
         patch("src.storage.vector_client.random.random", return_value=0.0):
        upsert_vector("test-id", [0.0] * VECTOR_DIMS, {})

    mock_index.fetch.assert_called_once_with(ids=["test-id"])


def test_wrong_dim_raises():
    with pytest.raises(AssertionError, match="Vector dim mismatch"):
        upsert_vector("bad-id", [0.0] * (VECTOR_DIMS - 1), {})
