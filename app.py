"""SmartLiva Application Entrypoint.

Starts the FastAPI server with modern CLI parameters and banner.
"""

import argparse
import uvicorn


def main() -> None:
    """Parse CLI arguments and launch the uvicorn web server."""
    parser = argparse.ArgumentParser(description="Start the SmartLiva Web Application & API Server.")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host IP to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    parser.add_argument("--reload", action="store_true", default=True, help="Enable auto-reload on code changes")
    args = parser.parse_args()

    print("=" * 65)
    print(" 🏥  SmartLiva: Liver Ultrasound Segmentation & Clinical AI")
    print(f" 🌐  Server running on http://localhost:{args.port}")
    print("=" * 65)

    uvicorn.run("src.api.server:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
