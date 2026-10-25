#!/usr/bin/env python3
"""
HONEST-BUT-SLOW clients. These are the hard negatives of the whole study:
legitimate users on bad links who still *complete* their requests. A good
detector must NOT isolate them. They differ from Slowloris in one key way:
the header block always terminates (CRLFCRLF) and a full response is read.
"""
import argparse
import random
import socket
import time


def slow_but_complete(ip, port, header_delay, n_headers):
    """Send a full request slowly, then read the response. Honest client."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(30)
    s.connect((ip, port))
    s.send(b"GET / HTTP/1.1\r\n")
    s.send(b"Host: victim\r\n")
    for i in range(n_headers):
        time.sleep(header_delay)              # slow link, but still progressing
        s.send(f"X-Slow-Link: chunk-{i}\r\n".encode())
    s.send(b"\r\n")                            # <-- headers DO terminate
    try:
        s.recv(65535)                          # read the response
    except OSError:
        pass
    s.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="victim")
    ap.add_argument("--port", type=int, default=80)
    ap.add_argument("--clients", type=int, default=15)
    ap.add_argument("--duration", type=float, default=120.0)
    args = ap.parse_args()
    ip = socket.gethostbyname(args.target)
    deadline = time.time() + args.duration
    print(f"[benign-slow] {args.clients} honest slow clients -> {ip}", flush=True)
    while time.time() < deadline:
        for _ in range(args.clients):
            try:
                slow_but_complete(ip, args.port,
                                  header_delay=random.uniform(0.3, 1.5),
                                  n_headers=random.randint(3, 8))
            except OSError:
                pass
        time.sleep(1.0)
    print("[benign-slow] done", flush=True)


if __name__ == "__main__":
    main()
