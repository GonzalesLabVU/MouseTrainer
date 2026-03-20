from __future__ import annotations

import os


APP_NAME = "MouseTrainer"
DEFAULT_APP_VERSION = "0.1.0"
APP_VERSION = str(os.getenv("MOUSETRAINER_APP_VERSION", DEFAULT_APP_VERSION)).strip() or DEFAULT_APP_VERSION
