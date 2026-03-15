import os

FEATURES_STREAM_NAME = os.getenv("FEATURES_STREAM_NAME", "metricade_features_stream")
CONSUMER_GROUP = os.getenv("CONSUMER_GROUP", "model_group")
CONSUMER_NAME = os.getenv("CONSUMER_NAME", "model_worker_1")
FEATURE_STORE_KEY_PREFIX = os.getenv("FEATURE_STORE_KEY_PREFIX", "metricade_features")
MODELS_DIR = os.getenv("MODELS_DIR", "/models")
VECTOR_DIMS = int(os.getenv("VECTOR_DIMS", "192"))
SPOT_CHECK_RATE = float(os.getenv("SPOT_CHECK_RATE", "0.01"))

# Must match feature-worker exactly
MAX_SEQ_LEN = 256
N_CONT = 40
N_CAT = 8
