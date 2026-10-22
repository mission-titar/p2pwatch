import socketserver


class FakeMetricsServer(socketserver.BaseServer):
    def shutdown(self) -> None: ...

    def server_close(self) -> None: ...
