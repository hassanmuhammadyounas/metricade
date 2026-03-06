import torch
import pytest
from src.inference.transformer import BehavioralTransformer
from src.constants import VECTOR_DIMS


def test_output_shape():
    model = BehavioralTransformer()
    model.eval()
    x = torch.zeros(1, 64, BehavioralTransformer.INPUT_DIM)
    with torch.no_grad():
        out = model(x)
    assert out.shape == (1, VECTOR_DIMS)


def test_output_dtype():
    model = BehavioralTransformer()
    model.eval()
    x = torch.zeros(1, 64, BehavioralTransformer.INPUT_DIM)
    with torch.no_grad():
        out = model(x)
    assert out.dtype == torch.float32


def test_output_is_l2_normalized():
    model = BehavioralTransformer()
    model.eval()
    x = torch.randn(1, 64, BehavioralTransformer.INPUT_DIM)
    with torch.no_grad():
        out = model(x)
    norm = out.norm(dim=-1).item()
    assert abs(norm - 1.0) < 1e-5


def test_encode_returns_list_of_correct_length():
    model = BehavioralTransformer()
    x = torch.zeros(64, BehavioralTransformer.INPUT_DIM)
    result = model.encode(x)
    assert isinstance(result, list)
    assert len(result) == VECTOR_DIMS
