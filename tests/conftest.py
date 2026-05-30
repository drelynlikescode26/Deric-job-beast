import sys
from pathlib import Path
from unittest.mock import MagicMock

# Make Auto-Applier importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Auto-Applier"))

# Stub out telegram_bot so tests don't need a live Telegram connection or the
# cryptography native extension (which is broken in some CI/cloud environments).
telegram_stub = MagicMock()
telegram_stub.send_message = MagicMock()
telegram_stub.send_photo = MagicMock()
sys.modules.setdefault("telegram_bot", telegram_stub)

# Also stub the underlying python-telegram-bot package to prevent import errors.
for mod in ("telegram", "telegram.ext", "telegram._payment", "telegram.ext._application"):
    sys.modules.setdefault(mod, MagicMock())
