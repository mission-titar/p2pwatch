import json
import threading
from http.server import BaseHTTPRequestHandler


class FakeNotificationSink(BaseHTTPRequestHandler):
    """Records each apprise ``json://`` notification: its User-Agent (the app_id) and title."""

    received: list[tuple[str, str]] = []
    _arrived = threading.Condition()

    @classmethod
    def wait_for(cls, notification: tuple[str, str], *, timeout_seconds: float) -> bool:
        """Blocks until ``notification`` is received, as ``Condition.wait_for`` does."""
        with cls._arrived:
            return cls._arrived.wait_for(lambda: notification in cls.received, timeout_seconds)

    def do_POST(self) -> None:  # http.server's name
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with self._arrived:
            self.received.append((self.headers["User-Agent"], body["title"]))
            self._arrived.notify_all()
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass  # stderr stays quiet
