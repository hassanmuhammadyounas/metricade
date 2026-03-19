import os

STREAM_NAME = os.getenv("STREAM_NAME", "metricade_stream")
CONSUMER_GROUP = os.getenv("CONSUMER_GROUP", "feature_group")
CONSUMER_NAME = os.getenv("CONSUMER_NAME", "feature_worker_1")
DLQ_KEY = os.getenv("DLQ_KEY", "metricade_dlq")
FEATURES_STREAM_NAME = os.getenv("FEATURES_STREAM_NAME", "metricade_features_stream")
FEATURE_STORE_KEY_PREFIX = os.getenv("FEATURE_STORE_KEY_PREFIX", "metricade_features")
# Sequence config
MAX_RAW_EVENTS = 2048        # max raw events to keep before merging
TOKEN_MERGE_FACTOR = 8       # merge N adjacent events into one token
MAX_SEQ_LEN = 256            # final sequence length fed to Transformer (MAX_RAW_EVENTS / TOKEN_MERGE_FACTOR)
N_CONT = 40                  # continuous features per event row — must match featurizer
N_CAT = 8                    # session-level categorical indices — must match featurizer
