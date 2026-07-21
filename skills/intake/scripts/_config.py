"""Shared config for intake. Everything personal is env-configurable."""
import os
from pathlib import Path

# Which knowledge domain new material is filed under. A vault with multiple
# projects can route by domain; a simple setup can ignore it entirely.
DEFAULT_DOMAIN = os.environ.get("INTAKE_DOMAIN", "default")

# Where --keep persists durable artifacts (cloned repos, kept media).
STORE_BASE = Path(os.path.expanduser(os.environ.get("INTAKE_STORE", "~/knowledge")))
