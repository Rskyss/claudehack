"""Offline regression tests; never read live credentials or contact an upstream."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

SOURCE = Path(os.environ.get('GATEWAY_SOURCE', Path(__file__).parents[1] / 'gateway/retry_proxy.py'))


def load_module():
    spec = importlib.util.spec_from_file_location('gateway_under_test', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SocketDouble:
    def __init__(self, response=b'HTTP/1.1 200 OK\r\n\r\n', fail_send=False):
        self.response = response
        self.fail_send = fail_send
        self.closed = False
        self.sent = []

    def setsockopt(self, *args): pass
    def settimeout(self, value): pass
    def close(self): self.closed = True
    def recv(self, size):
        data, self.response = self.response, b''
        return data
    def sendall(self, data):
        if self.fail_send:
            raise OSError('peer disconnected')
        self.sent.append(data)


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.gateway = load_module()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / 'residential.json'
        self.gateway.CONFIG_PATH = str(self.config)

    def write_config(self, **overrides):
        data = dict(host='proxy.invalid', port=12323, username='test', password='test-only')
        data.update(overrides)
        self.config.write_text(json.dumps(data))
        return data

    def test_missing_config_refuses_connection(self):
        with self.assertRaises(ConnectionError):
            self.gateway.load_residential_config()

    def test_corrupt_config_does_not_reuse_cached_credentials(self):
        self.write_config()
        self.gateway.load_residential_config()
        previous = self.config.stat().st_mtime
        self.config.write_text('{broken')
        os.utime(self.config, (previous + 2, previous + 2))
        with self.assertRaises(ConnectionError):
            self.gateway.load_residential_config()

    def test_invalid_fields_refuse_connection(self):
        for change in ({'host': ''}, {'port': 0}, {'port': 65536}, {'username': None}, {'password': ''}):
            with self.subTest(change=change):
                self.gateway._cfg_cache = {'mtime': 0, 'data': None}
                self.write_config(**change)
                with self.assertRaises(ConnectionError):
                    self.gateway.load_residential_config()

    def test_valid_config_hot_reload(self):
        self.write_config()
        self.assertEqual(self.gateway.load_residential_config()['host'], 'proxy.invalid')
        previous = self.config.stat().st_mtime
        self.write_config(host='replacement.invalid', port='2222')
        os.utime(self.config, (previous + 2, previous + 2))
        cfg = self.gateway.load_residential_config()
        self.assertEqual((cfg['host'], cfg['port']), ('replacement.invalid', 2222))

    def test_success_transfers_open_tunnel_with_extra_bytes(self):
        self.write_config()
        sock = SocketDouble(b'HTTP/1.1 200 OK\r\n\r\nextra')
        with patch.object(self.gateway.socket, 'create_connection', return_value=sock):
            result = self.gateway.connect_tunnel_race('example.com', 443)
        self.assertEqual(result, (sock, b'extra', 1))
        self.assertFalse(sock.closed)
        self.assertTrue(sock.sent[0].startswith(b'CONNECT example.com:443 HTTP/1.1\r\n'))
        sock.close()

    def test_timeout_closes_late_success_and_stops_workers(self):
        self.write_config()
        release = threading.Event()
        workers, sockets = [], []
        real_thread = threading.Thread

        class ShortJoinThread(real_thread):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                workers.append(self)
            def join(self, timeout=None):
                return super().join(0.001)

        def connect(*args, **kwargs):
            release.wait(3)
            sock = SocketDouble()
            sockets.append(sock)
            return sock

        with patch.object(self.gateway.threading, 'Thread', ShortJoinThread), patch.object(self.gateway.socket, 'create_connection', side_effect=connect):
            try:
                with self.assertRaises(ConnectionError):
                    self.gateway.connect_tunnel_race('example.com', 443)
            finally:
                release.set()
                for worker in workers:
                    real_thread.join(worker, 3)
        self.assertTrue(all(not t.is_alive() for t in workers))
        self.assertTrue(sockets)
        self.assertTrue(all(s.closed for s in sockets), 'late successful tunnel was orphaned')

    def test_rejected_tunnels_close_and_retry_budget_is_bounded(self):
        self.write_config()
        self.gateway.MAX_ATTEMPTS = 3
        sockets = []
        def connect(*args, **kwargs):
            sock = SocketDouble(b'HTTP/1.1 503 Unavailable\r\n\r\n')
            sockets.append(sock)
            return sock
        with patch.object(self.gateway.socket, 'create_connection', side_effect=connect):
            with self.assertRaises(ConnectionError):
                self.gateway.connect_tunnel_race('example.com', 443)
        self.assertEqual(len(sockets), 3)
        self.assertTrue(all(s.closed for s in sockets))

    def test_plain_http_send_failure_closes_acquired_tunnel(self):
        remote = SocketDouble(fail_send=True)
        with patch.object(self.gateway, 'connect_tunnel_race', return_value=(remote, b'', 1)):
            with self.assertRaises(OSError):
                self.gateway.forward_plain_http(b'GET http://example.com/ HTTP/1.1\r\nHost: example.com', b'')
        self.assertTrue(remote.closed)

    def test_client_disconnect_closes_acquired_tunnel(self):
        conn = SocketDouble(b'CONNECT example.com:443 HTTP/1.1\r\n\r\n', fail_send=True)
        remote = SocketDouble()
        with patch.object(self.gateway, 'connect_tunnel_race', return_value=(remote, b'', 1)), patch('builtins.print'):
            self.gateway.handle(conn)
        self.assertTrue(conn.closed)
        self.assertTrue(remote.closed)


if __name__ == '__main__':
    unittest.main()
