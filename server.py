#!/usr/bin/env python3
"""
Demo UI server — serves index.html and streams SSE events from the Apigee emulator.
Usage: python3 server.py
"""

import json
import time
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

PROXY_URL = "http://localhost:8998/ai-agent"
COST_PER_CALL = 0.002

SEMANTIC_INTENTS = [
    "find the best pizza restaurant near me",
    "what's a good pizza place around here?",
    "recommend a pizza restaurant nearby",
    "where can I get great pizza close to me?",
    "show me top-rated pizza spots in my area",
    "pizza restaurants near my location",
    "best pizza delivery near me",
]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._serve_file("index.html", "text/html; charset=utf-8")
        elif path == "/api/run":
            mode = parse_qs(urlparse(self.path).query).get("mode", ["after"])[0]
            self._stream(mode)
        else:
            self.send_response(404); self.end_headers()

    def _serve_file(self, name, ctype):
        try:
            data = open(name, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_response(404); self.end_headers()

    def _stream(self, mode):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        def emit(evt, data):
            try:
                self.wfile.write(f"event: {evt}\ndata: {json.dumps(data)}\n\n".encode())
                self.wfile.flush()
                return True
            except BrokenPipeError:
                return False

        try:
            if mode == "after":
                _run_after(emit)
            elif mode == "semantic":
                _run_semantic(emit)
        except Exception as ex:
            emit("error", {"message": str(ex)})


def _run_after(emit):
    hop, call = 0, 1
    cost = 0.0
    while True:
        req = urllib.request.Request(PROXY_URL)
        if hop > 0:
            req.add_header("X-Agent-Loop-Count", str(hop))
        try:
            with urllib.request.urlopen(req, timeout=5):
                cost += COST_PER_CALL
                if not emit("call", {"call": call, "hop": hop, "status": 200, "cost": round(cost, 3)}):
                    return
                hop += 1; call += 1
                time.sleep(0.18)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                body = json.loads(e.read().decode())
                emit("blocked", {"call": call, "hop": hop, "body": body})
            else:
                emit("error", {"code": e.code})
            return
        except Exception as ex:
            emit("error", {"message": str(ex)}); return


def _run_semantic(emit):
    history, hop = [], 0
    cost = 0.0
    for i, intent in enumerate(SEMANTIC_INTENTS):
        history.append(intent)
        if hop >= 3:
            emit("gemini_check", {"hop": hop, "count": len(history)})

        body = json.dumps({"intent": intent}).encode()
        req = urllib.request.Request(PROXY_URL, data=body)
        req.add_header("Content-Type", "application/json")
        req.add_header("X-Agent-Loop-Count", str(hop))
        req.add_header("X-Agent-History", "||".join(history[-5:]))

        try:
            with urllib.request.urlopen(req, timeout=10):
                cost += COST_PER_CALL
                if not emit("call", {"call": i + 1, "hop": hop, "status": 200,
                                     "intent": intent, "cost": round(cost, 3)}):
                    return
                hop += 1
                time.sleep(0.3)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                body_data = json.loads(e.read().decode())
                emit("blocked", {"call": i + 1, "hop": hop, "intent": intent, "body": body_data})
            else:
                emit("error", {"code": e.code})
            return
        except Exception as ex:
            emit("error", {"message": str(ex)}); return

    emit("done", {"message": "All intents passed — add more or lower threshold"})


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    server = ThreadedHTTPServer(("localhost", 3000), Handler)
    print("┌─────────────────────────────────────┐")
    print("│  Demo UI → http://localhost:3000    │")
    print("│  Ctrl-C to stop                     │")
    print("└─────────────────────────────────────┘")
    server.serve_forever()
