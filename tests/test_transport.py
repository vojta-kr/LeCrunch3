"""Transport behaviour against a scripted VICP peer on loopback. No oscilloscope needed."""

import socket
import struct
import threading
import time

import pytest

from LeCrunch3 import LeCrunch3


def vicp(payload):
    """Wrap `payload` in a VICP frame with the EOI bit set, as the scope does for a complete reply."""
    return struct.pack('>BBBBL', 0x81, 1, 1, 0, len(payload)) + payload


OK = vicp(b'CMR 0\n')  # the answer to the `cmr?` that check_last_command() sends
CLOSE = None  # close the connection instead of answering
SILENT = object()  # never answer, keep the connection open


class Peer:
    """Answer each query (a message containing '?') with the next scripted reply.

    Bare commands get no reply, like on the scope. `CLOSE` closes the connection
    instead of answering, `SILENT` keeps it open without answering, and the peer
    closes once its replies are used up.
    """

    def __init__(self, replies):
        self.replies = list(replies)
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        conn, _ = self.listener.accept()
        with conn:
            while self.replies:
                data = conn.recv(4096)
                if not data:
                    return
                if b'?' not in data:
                    continue
                reply = self.replies.pop(0)
                if reply is CLOSE:
                    return
                if reply is SILENT:
                    self.replies = []
                    conn.recv(4096)  # block until the client goes away
                    return
                conn.sendall(reply)

    def scope(self, timeout=1.0):
        # the constructor consumes two OK replies: comm_header and comm_format
        return LeCrunch3('127.0.0.1', port=self.port, timeout=timeout)


def test_recv_raises_when_peer_closes_before_the_header():
    scope = Peer([OK, OK, CLOSE]).scope()
    scope.send('*idn?')
    with pytest.raises(ConnectionError):
        scope.recv()


def test_recv_raises_when_peer_closes_mid_reply():
    partial = struct.pack('>BBBBL', 0x81, 1, 1, 0, 100) + b'0123456789'  # promises 100 bytes, sends 10
    scope = Peer([OK, OK, partial]).scope()
    scope.send('*idn?')
    with pytest.raises(ConnectionError):
        scope.recv()


def test_clear_raises_when_peer_has_closed():
    scope = Peer([OK, OK, CLOSE]).scope()
    scope.send('*idn?')
    time.sleep(0.2)  # let the peer close first
    with pytest.raises(ConnectionError):
        scope.clear()


def test_recv_times_out_when_peer_is_silent():
    scope = Peer([OK, OK, SILENT]).scope(timeout=0.3)
    scope.send('*idn?')
    t0 = time.monotonic()
    with pytest.raises(socket.timeout):
        scope.recv()
    assert time.monotonic() - t0 < 2.0


def test_accepts_a_connected_socket():
    peer = Peer([OK, OK])
    sock = socket.create_connection(('127.0.0.1', peer.port), timeout=1.0)
    scope = LeCrunch3('127.0.0.1', port=peer.port, timeout=0.7, sock=sock)
    assert scope.sock is sock
    assert sock.gettimeout() == 0.7


def test_connect_is_bounded_by_the_timeout():
    t0 = time.monotonic()
    with pytest.raises(OSError):
        LeCrunch3('10.255.255.1', port=1861, timeout=0.5)  # a black-hole address: nothing answers the SYN
    assert time.monotonic() - t0 < 3.0
