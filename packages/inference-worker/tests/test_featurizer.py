import torch
import pytest
from src.inference.featurizer import featurize, NUM_FEATURES, MAX_SEQ_LEN


def make_scroll_event(velocity=100.0, acceleration=10.0, reversal=0):
    return {
        "event_type": "SCROLL",
        "delta_ms": 200,
        "scroll_velocity_px_s": velocity,
        "scroll_acceleration": acceleration,
        "y_reversal": reversal,
        "scroll_depth_pct": 30,
    }


def test_output_shape():
    payload = {"events": [make_scroll_event() for _ in range(10)]}
    tensor = featurize(payload)
    assert tensor.shape == (MAX_SEQ_LEN, NUM_FEATURES)


def test_output_dtype():
    payload = {"events": [make_scroll_event()]}
    tensor = featurize(payload)
    assert tensor.dtype == torch.float32


def test_padding_fills_zeros():
    # Only 1 event — rest should be zero-padded
    payload = {"events": [make_scroll_event()]}
    tensor = featurize(payload)
    assert tensor[1:].sum().item() == 0.0


def test_scroll_event_type_one_hot():
    payload = {"events": [make_scroll_event()]}
    tensor = featurize(payload)
    # SCROLL is index 2 in the one-hot encoding
    assert tensor[0, 2].item() == 1.0


def test_empty_payload_returns_zeros():
    tensor = featurize({})
    assert tensor.shape == (MAX_SEQ_LEN, NUM_FEATURES)
    assert tensor.sum().item() == 0.0


def test_truncates_at_max_seq_len():
    payload = {"events": [make_scroll_event() for _ in range(MAX_SEQ_LEN + 20)]}
    tensor = featurize(payload)
    assert tensor.shape[0] == MAX_SEQ_LEN
