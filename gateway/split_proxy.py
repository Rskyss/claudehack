#!/usr/bin/env python3
"""本地 SOCKS5 兜底分流器（监听 127.0.0.1:8687）。

所有 Claude、Google 账号/Gmail/搜索、Stripe 支付收银台、人机验证盾、设备指纹探针及验真站域名
统一转发至核心住宅网关 127.0.0.1:8121。
大流量下载/更新子域及普通日常网站（含 YouTube 视频）直接放行，走日常系统网络通道（心安/RelyVPN）。
"""

import select
import socket
import threading

LISTEN = ("127.0.0.1", 8687)
RESIDENTIAL_GATEWAY = ("127.0.0.1", 8121)
IDLE_TIMEOUT = 1800

# 豁免走日常高速 VPN 的大流量下载、软件更新、云盘相册与日常翻译子域（节省住宅带宽）
BYPASS_SUFFIXES = (
    "dl.google.com",
    "drive.google.com",
    "docs.google.com",
    "photos.google.com",
    "takeout.google.com",
    "translate.google.com",
    "update.googleapis.com",
    "storage.googleapis.com",
    "commondatastorage.googleapis.com",
    "translate.googleapis.com",
)

SUFFIXES = (
    # 1. Claude / Anthropic 官方全系与客服组件
    "claude.ai",
    "claude.com",
    "anthropic.com",
    "claudeusercontent.com",
    "claudemcpclient.com",
    "claudemcpcontent.com",
    "anthropic.statuspage.io",
    "intercom.io",
    "intercomcdn.com",
    # 2. Google 纯净身份闭环（搜索、账号中心、OAuth 快捷登录、Gmail 邮箱、reCAPTCHA，不含 YouTube 视频）
    "google.com",
    "gmail.com",
    "googlemail.com",
    "accounts.youtube.com",
    "googleapis.com",
    "www.gstatic.com",
    "ssl.gstatic.com",
    "fonts.gstatic.com",
    "lh3.googleusercontent.com",
    "recaptcha.net",
    "withgoogle.com",
    # 3. Stripe 支付收银台与金融结算风控全系
    "stripe.com",
    "stripe.network",
    "stripecdn.com",
    "link.com",
    # 4. 人机验证盾全系（Cloudflare / hCaptcha / Arkose）
    "challenges.cloudflare.com",
    "csp-reporting.cloudflare.com",
    "cloudflareinsights.com",
    "cloudflareperf.com",
    "pat-issuer.cloudflare.com",
    "hcaptcha.com",
    "arkoselabs.com",
    "funcaptcha.com",
    # 5. 商业级反欺诈设备指纹与 KYC 身份核验全系
    "fpjs.io",
    "fpcdn.io",
    "fptls.com",
    "withpersona.com",
    "sift.com",
    "siftscience.com",
    # 6. Claude 前端真实用户监控、实验开关与地区合规组件
    "datadoghq.com",
    "browser-intake-datadoghq.com",
    "browser-intake-us3-datadoghq.com",
    "browser-intake-us5-datadoghq.com",
    "statsig.com",
    "statsigapi.net",
    "featuregates.org",
    "prodregistryv2.org",
    "beyondwickedmapping.org",
    "growthbook.io",
    "segment.io",
    "segment.com",
    "rudderstack.com",
    "rudderlabs.com",
    "ingest.us.sentry.io",
    "ingest.sentry.io",
    "onetrust.com",
    "cookielaw.org",
    # 7. 全网主流环境 / IP / 指纹泄露验真站
    "ippure.com",
    "ipin.io",
    "ipinfo.io",
    "ipinfo.cv",
    "ipapi.co",
    "ipip.net",
    "ipify.org",
    "icanhazip.com",
    "ip.sb",
    "net.coffee",
    "ipkk.com",
    "ipchaxun.net",
    "123169.xyz",
    "999831.xyz",
    "ip138.com",
    "ping0.cc",
    "scamalytics.com",
    "whoer.net",
    "browserleaks.com",
    "browserleaks.net",
    "browserleaks.org",
    "creepjs.com",
)


def is_claude(host):
    """判断目标域名是否属于美东静态住宅专线保护范围。"""
    name = host.lower().rstrip(".")
    if not name or name.replace(".", "").isdigit():
        return False
    try:
        socket.inet_pton(socket.AF_INET, name)
        return False
    except OSError:
        pass
    try:
        socket.inet_pton(socket.AF_INET6, name)
        return False
    except OSError:
        pass
    if any(name == b or name.endswith("." + b) for b in BYPASS_SUFFIXES):
        return False
    return any(name == suffix or name.endswith("." + suffix) for suffix in SUFFIXES)


def recvall(sock, size):
    buf = b""
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise ConnectionError("short read")
        buf += chunk
    return buf


def read_request(conn):
    version, nmethods = recvall(conn, 2)
    if version != 5:
        raise ConnectionError("not socks5")
    recvall(conn, nmethods)
    conn.sendall(b"\x05\x00")
    version, cmd, _rsv, atyp = recvall(conn, 4)
    if version != 5 or cmd != 1:
        raise ConnectionError("unsupported command")
    if atyp == 1:
        host = socket.inet_ntoa(recvall(conn, 4))
    elif atyp == 3:
        length = recvall(conn, 1)[0]
        host = recvall(conn, length).decode("utf-8", "replace")
    elif atyp == 4:
        host = socket.inet_ntop(socket.AF_INET6, recvall(conn, 16))
    else:
        raise ConnectionError("bad address")
    port = int.from_bytes(recvall(conn, 2), "big")
    return host, port


def reply(conn, code):
    conn.sendall(b"\x05" + bytes([code]) + b"\x00\x01\x00\x00\x00\x00\x00\x00")


def via_residential_gateway(host, port):
    """通过本地 8121 住宅网关建立隧道连接。"""
    remote = socket.create_connection(RESIDENTIAL_GATEWAY, timeout=25)
    target = host
    if ":" in host and not host.startswith("["):
        target = "[" + host + "]"
    remote.sendall(
        "CONNECT {0}:{1} HTTP/1.1\r\nHost: {0}:{1}\r\n\r\n".format(target, port).encode()
    )
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = remote.recv(4096)
        if not chunk:
            remote.close()
            raise ConnectionError("residential gateway closed")
        buf += chunk
        if len(buf) > 65536:
            remote.close()
            raise ConnectionError("gateway header too large")
    head, extra = buf.split(b"\r\n\r\n", 1)
    status = head.split(b"\r\n", 1)[0]
    if b" 200 " not in status:
        remote.close()
        raise ConnectionError(status.decode("latin1", "replace"))
    return remote, extra


def connect_direct(host, port):
    return socket.create_connection((host, port), timeout=20), b""


def pipe(left, right):
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
    host = "?"
    try:
        conn.settimeout(25)
        host, port = read_request(conn)
        if is_claude(host):
            remote, extra = via_residential_gateway(host, port)
            route = "residential"
        else:
            remote, extra = connect_direct(host, port)
            route = "direct"
        print("{0} {1}:{2}".format(route, host, port), flush=True)
        reply(conn, 0)
        if extra:
            conn.sendall(extra)
        conn.settimeout(None)
        remote.settimeout(None)
        pipe(conn, remote)
    except Exception as exc:
        print("fail {0}: {1}".format(host, exc), flush=True)
        try:
            reply(conn, 5)
        except Exception:
            pass
        try:
            conn.close()
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
