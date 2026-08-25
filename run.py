"""SmartLiva One-Click Launcher.

Launches the complete SmartLiva Clinical AI Web Application & API Server.
Usage:
    python run.py
    python run.py --port 8000 --host 0.0.0.0
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import uvicorn


def print_banner(host: str, port: int) -> None:
    banner = f"""
======================================================================
 🏥  SMARTLIVA: Liver Ultrasound Clinical AI & Screening Copilot
======================================================================
 🛡️  Gatekeeper: 10-Class Organ Classifier & Physics Gate Active
 🫀  Segmentation: Multi-Organ Gated (Liver + Gallbladder) Active
 🧬  Specialists: Fibrosis (F0-F4), Steatosis (S0-S3), YOLO Lesions
 🗄️  Data Flywheel: SQLite Database Active (Stage 2: Shadow Study)
 🌐  Web Application: http://localhost:{port}
 📖  API Documentation: http://localhost:{port}/docs
======================================================================
"""
    print(banner)


def main():
    parser = argparse.ArgumentParser(description="Launch the SmartLiva Web Application & API Server.")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host IP to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    parser.add_argument("--reload", action="store_true", default=False, help="Enable auto-reload on code changes")
    args = parser.parse_args()

    print_banner(args.host, args.port)
    uvicorn.run("src.api.server:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
