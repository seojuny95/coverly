import os

# Unit tests must remain deterministic even when a developer has DATABASE_URL configured.
os.environ["REFERENCE_DATA_DATABASE_ENABLED"] = "false"
