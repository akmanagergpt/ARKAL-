#!/usr/bin/env python3
"""Serve one built SPA with history-API fallback on loopback only."""

from __future__ import annotations

import argparse
import pathlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class SpaHandler(SimpleHTTPRequestHandler):
    def send_head(self):  # noqa: ANN201
        requested = pathlib.Path(self.directory) / self.path.lstrip("/").split("?", 1)[0]
        if self.path != "/" and not requested.exists():
            self.path = "/index.html"
        return super().send_head()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    handler = lambda *values, **kwargs: SpaHandler(  # noqa: E731
        *values, directory=args.directory, **kwargs,
    )
    ThreadingHTTPServer(("127.0.0.1", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
