#!/usr/bin/env python3
"""Claude 静态住宅 IP 核心本地网关（监听 127.0.0.1:8121）。

核心特性：
1. 直连静态住宅 HTTP 代理通道（由 residential.json 提供），支持配置文件热加载。
2. 错峰微并发 + 渐进退避重连（平抑支付结账页几十路并发请求触发的上游瞬时 403/503 抖动，消除偶发 502）。
3. 同时支持 HTTPS (CONNECT 隧道) 与普通 HTTP 请求转发。
4. 严格熔断（Fail-Closed）：住宅节点不可用时直接拒绝连接，绝不回退到日常 VPN。
"""

import base64
import json
import os
import select
import socket
import threading
import time

LISTEN = ("127.0.0.1", 8121)
CONFIG_PATH = os.path.expanduser("~/.config/claude-residential/residential.json")
MAX_ATTEMPTS = 36
RACE_WORKERS = 3
IDLE_TIMEOUT = 1800  # 30 分钟长连接保活，适配 Claude 深度思考模式

_cfg_cache = {"mtime": 0.0, "data": None}
_cfg_lock = threading.Lock()


def load_residential_config():
    """热加载住宅节点配置，修改 residential.json 后无需重启自动生效。"""
    try:
        st = os.stat(CONFIG_PATH)
        with _cfg_lock:
            if _cfg_cache["data"] is not None and st.st_mtime == _cfg_cache["mtime"]:
                return _cfg_cache["data"]
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if any(not isinstance(raw.get(key), str) or not raw[key].strip()
                   for key in ("host", "username", "password")):
                raise ValueError("invalid proxy configuration")
            port = int(raw["port"])
            if not 1 <= port <= 65535:
                raise ValueError("invalid proxy port")
            token = base64.b64encode(
                "{0}:{1}".format(raw["username"], raw["password"]).encode("utf-8")
            ).decode("ascii")
            parsed = {
                "host": raw["host"],
                "port": port,
                "auth_header": "Proxy-Authorization: Basic {0}\r\n".format(token),
            }
            _cfg_cache["mtime"] = st.st_mtime
            _cfg_cache["data"] = parsed
            return parsed
    except Exception:
        # 配置缺失或损坏时拒绝新连接，不使用旧凭据或内置备用配置。
        raise ConnectionError("residential proxy configuration unavailable or invalid") from None



def tune_socket(sock):
    """启用低延迟与 TCP 保活，防止长思考阶段断流。"""
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except Exception:
        pass


def recvall_until(sock, marker, limit=65536):
    """读取数据直到出现指定分隔符。"""
    buf = b""
    while marker not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
        if len(buf) > limit:
            break
    return buf


def connect_tunnel_race(host, port):
    """通过错峰微并发竞速与渐进退避同住宅节点建立 CONNECT 加密隧道。"""
    cfg = load_residential_config()
    upstream_addr = (cfg["host"], cfg["port"])
    target = host
    if ":" in host and not host.startswith("["):
        target = "[" + host + "]"
    req = (
        "CONNECT {0}:{1} HTTP/1.1\r\n"
        "Host: {0}:{1}\r\n"
        "{2}"
        "Proxy-Connection: Keep-Alive\r\n\r\n"
    ).format(target, port, cfg["auth_header"]).encode("latin1")

    winner = [None]
    last_err = ["upstream timeout"]
    attempts = [0]
    lock = threading.Lock()
    done = threading.Event()

    def worker(worker_idx):
        local_round = 0
        while not done.is_set():
            with lock:
                if done.is_set() or attempts[0] >= MAX_ATTEMPTS:
                    return
                attempts[0] += 1
                cur_attempt = attempts[0]
            local_round += 1
            sock = None
            try:
                sock = socket.create_connection(upstream_addr, timeout=7)
                if done.is_set():
                    return
                tune_socket(sock)
                sock.settimeout(7)
                sock.sendall(req)
                head = recvall_until(sock, b"\r\n\r\n")
                status = head.split(b"\r\n", 1)[0]
                if b" 200 " in status:
                    extra = head.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in head else b""
                    with lock:
                        if winner[0] is None and not done.is_set():
                            winner[0] = (sock, extra, cur_attempt)
                            sock = None  # 移交 socket 所有权给主线程
                            done.set()
                            return
                else:
                    with lock:
                        last_err[0] = status.decode("latin1", "replace") or "bad status"
            except Exception as exc:
                with lock:
                    last_err[0] = str(exc)
            finally:
                if sock is not None:
                    try:
                        sock.close()
                    except Exception:
                        pass
            if not done.is_set():
                # 渐进退避（80ms -> 160ms -> 260ms），避开多请求并发时的瞬时脉冲窗口
                backoff = min(0.08 * local_round + 0.03 * worker_idx, 0.35)
                done.wait(backoff)

    threads = []
    for idx in range(RACE_WORKERS):
        t = threading.Thread(target=worker, args=(idx,), daemon=True)
        t.start()
        threads.append(t)
        if idx == 0:
            # 首路连接先独自尝试 150ms，一次命中则不启动额外并发，减少上游负载
            if done.wait(0.15):
                break
        else:
            if done.wait(0.08):
                break

    for t in threads:
        if done.is_set():
            break
        t.join(timeout=16)

    with lock:
        # 与 winner 移交共用锁，禁止超时返回后再产生无人接收的成功连接。
        done.set()
        if winner[0] is None:
            raise ConnectionError(last_err[0])
        return winner[0]


def forward_plain_http(raw_head, body_rest):
    """将普通明文 HTTP 代理请求自动转换为竞速隧道请求转发，共享竞速防抖能力。"""
    from urllib.parse import urlsplit

    lines = raw_head.split(b"\r\n")
    req_parts = lines[0].decode("latin1", "replace").split()
    method, full_url = req_parts[0], req_parts[1]
    version = req_parts[2] if len(req_parts) > 2 else "HTTP/1.1"

    parsed = urlsplit(full_url)
    host = parsed.hostname or ""
    port = parsed.port or 80
    path = parsed.path or "/"
    if parsed.query:
        path = "{0}?{1}".format(path, parsed.query)

    if not host:
        for line in lines[1:]:
            if line.lower().startswith(b"host:"):
                hval = line.split(b":", 1)[1].strip().decode("latin1", "replace")
                if ":" in hval and not hval.endswith("]"):
                    host, port_s = hval.rsplit(":", 1)
                    port = int(port_s)
                else:
                    host = hval
                break

    remote, extra, tries = connect_tunnel_race(host, port)
    new_lines = ["{0} {1} {2}".format(method, path, version).encode("latin1")]
    for line in lines[1:]:
        low = line.lower()
        if low.startswith(b"proxy-authorization:") or low.startswith(b"proxy-connection:"):
            continue
        new_lines.append(line)
    outbound = b"\r\n".join(new_lines) + b"\r\n\r\n" + body_rest
    try:
        remote.sendall(outbound)
    except Exception:
        remote.close()
        raise
    return remote, extra, tries


def pipe(left, right):
    """双向转发数据流。"""
    pair = [left, right]
    try:
        while True:
            ready, _, _ = select.select(pair, [], [], IDLE_TIMEOUT)
            if not ready:
                return
            for sock in ready:
                data = sock.recv(65536)
                if not data:
                    return
                other = right if sock is left else left
                other.sendall(data)
    except Exception:
        return
    finally:
        for sock in pair:
            try:
                sock.close()
            except Exception:
                pass


def handle(conn):
    """处理单个客户端代理连接。"""
    remote = None
    try:
        tune_socket(conn)
        conn.settimeout(25)
        data = recvall_until(conn, b"\r\n\r\n")
        if not data or b"\r\n" not in data:
            conn.close()
            return

        head_bytes, body_rest = (data.split(b"\r\n\r\n", 1) + [b""])[:2]
        first_line = head_bytes.split(b"\r\n", 1)[0].decode("latin1", "replace")
        parts = first_line.split()
        if len(parts) < 2:
            conn.close()
            return

        method = parts[0].upper()
        if method == "CONNECT":
            host, _, port_s = parts[1].rpartition(":")
            host = host.strip("[]")
            port = int(port_s or "443")
            remote, extra, tries = connect_tunnel_race(host, port)
            conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            if extra:
                conn.sendall(extra)
            if body_rest:
                remote.sendall(body_rest)
            print("ok {0}:{1} (tries={2})".format(host, port, tries), flush=True)
            conn.settimeout(None)
            remote.settimeout(None)
            pipe(conn, remote)
        else:
            remote, extra, tries = forward_plain_http(head_bytes, body_rest)
            if extra:
                conn.sendall(extra)
            print("ok-http {0} (tries={1})".format(parts[1], tries), flush=True)
            conn.settimeout(None)
            remote.settimeout(None)
            pipe(conn, remote)
    except Exception as exc:
        print("fail {0}".format(exc), flush=True)
        try:
            conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    finally:
        if remote is not None:
            try:
                remote.close()
            except Exception:
                pass


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(LISTEN)
    server.listen(256)
    print("listening {0}:{1}".format(*LISTEN), flush=True)
    while True:
        conn, _addr = server.accept()
        threading.Thread(target=handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
