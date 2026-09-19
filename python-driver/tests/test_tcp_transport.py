import socket
import threading
import unittest

from ups_simulator import SocketLineTransport


class OneShotServer:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.host, self.port = self.sock.getsockname()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.received = b""

    def start(self):
        self.thread.start()

    def _run(self):
        conn, _ = self.sock.accept()
        with conn:
            # Match the firmware behavior and deliberately put both greeting
            # lines in the same TCP write/packet opportunity.
            conn.sendall(
                b"OK NutUPS Ethernet HID UPS Simulator v1\r\n"
                b"OK simulator starts DISARMED; use ARM ON before changing UPS state\r\n"
            )
            while b"\n" not in self.received:
                chunk = conn.recv(256)
                if not chunk:
                    return
                self.received += chunk
            if self.received.strip() == b"PING":
                conn.sendall(b"OK PONG\r\n")
            else:
                conn.sendall(b"ERR unexpected command\r\n")
        self.sock.close()

    def join(self):
        self.thread.join(timeout=2.0)


class TcpTransportTests(unittest.TestCase):
    def test_two_line_greeting_is_fully_drained(self):
        server = OneShotServer()
        server.start()
        transport = SocketLineTransport(server.host, server.port, timeout=1.0)
        try:
            transport.connect()
            self.assertEqual(len(transport.greeting), 2)
            self.assertIn("NutUPS", transport.greeting[0])
            self.assertIn("DISARMED", transport.greeting[1])
            self.assertEqual(transport.command("PING"), "OK PONG")
        finally:
            transport.close()
            server.join()


if __name__ == "__main__":
    unittest.main()
