"""Entry point: start the dashboard backend server."""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from app.config import get_settings


def main():
    settings = get_settings()
    uvicorn.run(
        "app.api.main:create_app",
        factory=True,
        host=settings.server.host,
        port=settings.server.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
