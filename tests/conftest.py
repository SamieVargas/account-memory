"""Every test runs without the network. Hugging Face is put in offline mode
before anything imports it, so a test that tries to download a model fails
instead of quietly fetching one."""

import os

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
