#!/usr/bin/env python3
"""Servidor HTTP com CORS para servir cliente HTML."""
from http.server import HTTPServer, SimpleHTTPRequestHandler
import sys


class CORSHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE"
        )
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-Requested-With",
        )
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    server = HTTPServer(("0.0.0.0", port), CORSHandler)
    print(f"✓ Servidor HTTP em http://localhost:{port}")
    server.serve_forever()
