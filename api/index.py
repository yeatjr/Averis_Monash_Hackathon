import sys
from pathlib import Path

# Add project root to path so all imports work
ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

# Import your existing FastAPI app
from web.app import app
