"""Run the annotation web application."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from webapp.db import init_db
from webapp.app import app

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    print(f"Starting annotation app on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
