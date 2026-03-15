from .model_registry import get_model

def load_bootstrap_model():
    """Used only for health check validation at startup."""
    return get_model("__bootstrap__")
