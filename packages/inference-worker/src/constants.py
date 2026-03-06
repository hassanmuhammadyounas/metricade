import os

STREAM_NAME = os.getenv("STREAM_NAME", "behavioral_stream")
CONSUMER_GROUP = os.getenv("CONSUMER_GROUP", "inference_group")
CONSUMER_NAME = os.getenv("CONSUMER_NAME", "fly_worker_1")
DLQ_KEY = os.getenv("DLQ_KEY", "behavioral_dlq")
HEARTBEAT_KEY = os.getenv("HEARTBEAT_KEY", "fly_worker_heartbeat")
HEARTBEAT_INTERVAL_S = int(os.getenv("HEARTBEAT_INTERVAL_S", "30"))
VECTOR_DIMS = int(os.getenv("VECTOR_DIMS", "192"))
MODEL_PATH = os.getenv("MODEL_PATH", "/models/v1_simclr_trained.pt")
BOOTSTRAP_MODEL_PATH = os.getenv("BOOTSTRAP_MODEL_PATH", "/models/bootstrap_random.pt")
SPOT_CHECK_RATE = float(os.getenv("SPOT_CHECK_RATE", "0.01"))
