import socket
import threading
import unittest

from ups_simulator import CommandError, UpsSimulator


GREETING = b"OK NutUPS HID Simulator v2\r\nOK DISARMED\r\n"


class FirmwareLikeServer:
    """Line server mimicking UPS_Simulator_Ethernet.ino.

    greet_on_connect=False reproduces the old shipped firmware, where
    EthernetServer::available() only returned a client after data arrived.
    """

    def __init__(self, greet_on_connect):
        self.greet_on_connect = greet_on_connect
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.host, self.port = self.sock.getsockname()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        conn, _ = self.sock.accept()
        with conn:
            greeted = self.greet_on_connect
            if greeted:
                conn.sendall(GREETING)
            buf = b""
            while True:
                chunk = conn.recv(256)
                if not chunk:
                    break
                if not greeted:
                    conn.sendall(GREETING)
                    greeted = True
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    cmd = line.strip().upper()
                    if cmd == b"PING":
                        conn.sendall(b"OK PONG\r\n")
                    elif cmd == b"IDENT?":
                        conn.sendall(b"OK NutUPS HID Simulator v2\r\n")
                    elif cmd == b"AC OFF":
                        conn.sendall(b"ERR disarmed\r\n")
                    else:
                        conn.sendall(b"ERR command\r\n")
        self.sock.close()

    def join(self):
        self.thread.join(timeout=2.0)


class TcpTransportTests(unittest.TestCase):
    def _check(self, greet_on_connect):
        server = FirmwareLikeServer(greet_on_connect)
        sim = UpsSimulator.tcp(server.host, server.port, timeout=1.0)
        try:
            sim.connect()
            self.assertEqual(len(sim.transport.greeting), 2)
            self.assertIn("NutUPS", sim.transport.greeting[0])
            self.assertIn("DISARMED", sim.transport.greeting[1])
            self.assertTrue(sim.ping())
            self.assertEqual(sim.identify(), "NutUPS HID Simulator v2")
            with self.assertRaises(CommandError):
                sim.set_ac(False)
        finally:
            sim.close()
            server.join()

    def test_greeting_sent_on_connect(self):
        self._check(greet_on_connect=True)

    def test_greeting_sent_after_first_command_like_old_firmware(self):
        self._check(greet_on_connect=False)


if __name__ == "__main__":
    unittest.main()
