"""The service must not print a traceback when a client goes away.

A browser that navigates away mid-request, or a poller that abandons a
connection between the request and the response, makes the write fail.
The stdlib treats that as an unhandled exception and prints the whole
traceback, so ordinary use buried the real errors under thousands of
lines of noise. One session of ordinary IDE polling produced 3712 lines,
the majority of them ConnectionAbortedError from abandoned requests.

A genuine server-side fault must still propagate and still be reported.
"""

import io
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime import AgentRuntime, RuntimeConfig  # noqa: E402
from service import serve  # noqa: E402


class TestAbandonedConnections(unittest.TestCase):
    """A real client that disconnects before the response is written."""

    def _serve(self):
        tmp = Path(tempfile.mkdtemp(prefix="v10_abandoned_"))
        runtime = AgentRuntime(RuntimeConfig(
            allowed_workspace_roots=[str(tmp)]))
        server = serve(runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, tmp

    def _abandon(self, port: int) -> None:
        """Send a request and hang up before reading the response."""
        sock = socket.create_connection(("127.0.0.1", port), timeout=10)
        try:
            sock.sendall(b"GET /v1/runtime HTTP/1.1\r\n"
                         b"Host: 127.0.0.1\r\n"
                         b"Connection: close\r\n\r\n")
            # Give the server a moment to start writing, then hang up.
            sock.settimeout(0.05)
            try:
                sock.recv(1)
            except (socket.timeout, OSError):
                pass
        finally:
            sock.close()

    def test_an_abandoned_request_produces_no_traceback(self):
        server, tmp = self._serve()
        port = server.server_address[1]
        try:
            # The server's error output is captured so the test can see
            # what an operator would see.
            captured = io.StringIO()
            original = sys.stderr
            sys.stderr = captured
            try:
                for _ in range(5):
                    self._abandon(port)
                # Let the handler threads finish.
                threading.Event().wait(1.5)
            finally:
                sys.stderr = original
            noise = captured.getvalue()
            self.assertNotIn("Traceback", noise,
                             "an abandoned request produced a traceback:\n"
                             + noise[:2000])
            self.assertNotIn("ConnectionAbortedError", noise)
            self.assertNotIn("ConnectionResetError", noise)
        finally:
            server.shutdown()
            server.server_close()
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_service_still_serves_afterwards(self):
        """Swallowing the connection failures must not break the service."""
        server, tmp = self._serve()
        port = server.server_address[1]
        try:
            for _ in range(3):
                self._abandon(port)
            threading.Event().wait(0.5)
            import urllib.request
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/v1/runtime", timeout=15) as res:
                body = res.read().decode("utf-8")
            self.assertIn("health", body)
        finally:
            server.shutdown()
            server.server_close()
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
