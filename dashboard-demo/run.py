"""
Entrypoint for hosts where you CANNOT run shell commands (e.g. Pterodactyl /
Endercloud). The panel's egg typically runs something like `python run.py`,
so we boot uvicorn programmatically here instead of typing a uvicorn command.

Port: Pterodactyl injects the allocated port via the SERVER_PORT env var.
We MUST bind to 0.0.0.0 and that port to be reachable from outside.
"""

import os
import uvicorn

if __name__ == "__main__":
    # SERVER_PORT = Pterodactyl. PORT = many PaaS. 8000 = local fallback.
    port = int(os.environ.get("SERVER_PORT") or os.environ.get("PORT") or 8000)
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
