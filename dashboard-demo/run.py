"""
Entrypoint. Works anywhere `python run.py` runs - including hosts with no
shell access (Pterodactyl/Endercloud) and Termux/Android.

Port: Pterodactyl injects the allocated port via SERVER_PORT. We MUST bind to
0.0.0.0 and that port to be reachable from outside.

NOTE: Flask's built-in server (app.run) is fine for testing/learning. For a
real public deployment use a pure-Python WSGI server like waitress:
    pip install waitress
    waitress-serve --host=0.0.0.0 --port=$SERVER_PORT app.main:app
(waitress is pure Python too, so it also installs cleanly on Termux.)
"""

import os
from app.main import app

if __name__ == "__main__":
    # SERVER_PORT = Pterodactyl. PORT = many PaaS. 8000 = local fallback.
    port = int(os.environ.get("SERVER_PORT") or os.environ.get("PORT") or 8000)
    app.run(host="0.0.0.0", port=port)
