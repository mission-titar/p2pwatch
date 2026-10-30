import json
from http.server import BaseHTTPRequestHandler


class FakeNotificationSink(BaseHTTPRequestHandler):
    """Records each apprise ``json://`` notification: its User-Agent (the app_id) and title."""

    received: list[tuple[str, str]] = []

    def do_POST(self) -> None:  # http.server's name
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.received.append((self.headers["User-Agent"], body["title"]))
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass  # stderr stays quiet
