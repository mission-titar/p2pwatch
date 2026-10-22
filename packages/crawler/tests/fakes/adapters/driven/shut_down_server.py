import socketserver


class ShutDownServer(socketserver.BaseServer):
    def shutdown(self) -> None: ...

    def server_close(self) -> None: ...
