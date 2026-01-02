import os
import sys
from pathlib import Path


# Ensure project root is on sys.path for imports like `import app`, `import core`
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Use a lightweight SQLite DB during tests
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("HIGHLIGHTS_BASE_PATH", str(ROOT / "sample-highlights"))
