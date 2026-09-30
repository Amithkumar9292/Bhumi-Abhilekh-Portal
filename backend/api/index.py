"""Vercel serverless entrypoint.

Vercel's zero-config Python detection only looks for a top-level `main.py` or
`app.py`. This project's ASGI application lives at `app/main.py`, which is a
package, not a module at the root, so detection cannot find it and the project
would build successfully but serve 404 on every route.

`vercel.json` points the `@vercel/python` builder at this file and routes every
path to it. Re-exporting `app` is all the entrypoint needs: the object below is
the ASGI callable Vercel hands each request to.
"""

from app.main import app

__all__ = ["app"]
