import numpy as np
import pytest
from src.labeler import _apply_rules, FEAT_SCROLL_VELOCITY, FEAT_Y_REVERSAL, FEAT_SCROLL_DEPTH


def make_profile(**overrides) -> np.ndarray:
    """Create a 51-feature profile with all zeros, then apply overrides."""
    profile = np.zeros(51, dtype=np.float32)
    for key, value in overrides.items():
        profile[key] = value
    return profile


def test_fraud_bot_velocity_threshold():
    """velocity > 180 px/s (0.18 normalized) and near-zero reversals → FRAUD_BOT"""
    profile = make_profile(**{
        FEAT_SCROLL_VELOCITY: 0.19,   # 190 px/s after *1000 normalization
        FEAT_Y_REVERSAL: 0.00,
    })
    assert _apply_rules(profile) == "FRAUD_BOT"


def test_not_fraud_bot_with_reversals():
    """High velocity BUT has reversals → not FRAUD_BOT"""
    profile = make_profile(**{
        FEAT_SCROLL_VELOCITY: 0.19,
        FEAT_Y_REVERSAL: 0.10,
        FEAT_SCROLL_DEPTH: 0.70,
    })
    assert _apply_rules(profile) == "HIGH_INTENT"


def test_high_intent_deep_with_reversals():
    """Deep scroll + reversals → HIGH_INTENT"""
    profile = make_profile(**{
        FEAT_SCROLL_VELOCITY: 0.05,
        FEAT_Y_REVERSAL: 0.08,
        FEAT_SCROLL_DEPTH: 0.65,
    })
    assert _apply_rules(profile) == "HIGH_INTENT"


def test_medium_intent_moderate_depth():
    profile = make_profile(**{
        FEAT_SCROLL_DEPTH: 0.40,
        FEAT_Y_REVERSAL: 0.02,
    })
    assert _apply_rules(profile) == "MEDIUM_INTENT"


def test_low_intent_shallow_scroll():
    profile = make_profile(**{
        FEAT_SCROLL_DEPTH: 0.10,
        FEAT_Y_REVERSAL: 0.01,
    })
    assert _apply_rules(profile) == "LOW_INTENT"
