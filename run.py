"""Run the self-hosted distribution from its own directory."""
import argparse
import os
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="启动 Serenita 自部署工作区")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    options = parser.parse_args()
    os.environ["SERENITA_SERVICE_MODE"] = "self_hosted"
    os.environ.setdefault("DATA_ROOT", str(root / "serenita_self_hosted_data"))
    os.environ["SERENITA_FRONTEND_ROOT"] = str(root / "web" if (root / "web").is_dir() else root / "frontend" / "dist")
    import uvicorn
    uvicorn.run("backend.app.main:create_app", factory=True, host=options.host, port=options.port)


if __name__ == "__main__":
    main()
