"""
Per-connection flow tracking and feature extraction.

The feature set is deliberately tuned to Slowloris's low-and-slow signature and
includes a LAYER-7 feature (header completion) that flow-only tools such as
CICFlowMeter cannot produce. A flow is keyed by (src_ip, src_port).
"""
import threading
import time
from dataclasses import dataclass, field
from statistics import mean, pstdev

# Order matters: train.py and detect.py rely on this exact column order.
FEATURE_NAMES = [
    "duration",            # seconds the flow has been open
    "bytes_in",            # payload bytes from client -> server
    "bytes_per_sec",       # throughput; Slowloris is near-zero
    "pkt_count",           # client->server packets
    "mean_iat",            # mean inter-arrival time of client packets
    "std_iat",             # regularity of trickle; Slowloris is very regular
    "idle_time",           # seconds since last client byte
    "header_lines",        # count of CRLF-delimited header lines seen
    "headers_complete",    # 1 if CRLFCRLF seen (request fully formed) else 0
    "incomplete_ratio",    # 1 - headers_complete, kept explicit for the model
    "small_pkt_ratio",     # fraction of client packets < 64 B payload
    "conns_from_src",      # concurrent open flows from the same source IP
]

CRLFCRLF = b"\r\n\r\n"


@dataclass
class Flow:
    src_ip: str
    src_port: int
    start: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    bytes_in: int = 0
    pkt_count: int = 0
    small_pkts: int = 0
    iats: list = field(default_factory=list)
    buf: bytes = b""              # bounded header buffer
    headers_complete: int = 0
    closed: bool = False

    def update(self, payload: bytes, now: float):
        if self.pkt_count > 0:
            self.iats.append(now - self.last_seen)
        self.last_seen = now
        self.pkt_count += 1
        self.bytes_in += len(payload)
        if len(payload) < 64:
            self.small_pkts += 1
        if not self.headers_complete and payload:
            # keep only the first 8 KiB; enough to see the header terminator
            self.buf = (self.buf + payload)[:8192]
            if CRLFCRLF in self.buf:
                self.headers_complete = 1

    def features(self, now: float, conns_from_src: int) -> dict:
        dur = max(1e-3, now - self.start)
        header_lines = self.buf.count(b"\r\n")
        return {
            "duration": dur,
            "bytes_in": self.bytes_in,
            "bytes_per_sec": self.bytes_in / dur,
            "pkt_count": self.pkt_count,
            "mean_iat": mean(self.iats) if self.iats else 0.0,
            "std_iat": pstdev(self.iats) if len(self.iats) > 1 else 0.0,
            "idle_time": now - self.last_seen,
            "header_lines": header_lines,
            "headers_complete": self.headers_complete,
            "incomplete_ratio": 1 - self.headers_complete,
            "small_pkt_ratio": self.small_pkts / max(1, self.pkt_count),
            "conns_from_src": conns_from_src,
        }


class FlowTable:
    """Holds live flows, expires idle ones, and emits feature rows."""

    def __init__(self, server_port: int = 80, expire_after: float = 30.0):
        self.server_port = server_port
        self.expire_after = expire_after
        self.flows: dict[tuple[str, int], Flow] = {}
        self._lock = threading.Lock()   # sniffer thread vs. snapshot thread

    def on_packet(self, src_ip, src_port, dst_port, payload, now=None):
        now = now or time.time()
        if dst_port != self.server_port:
            return  # only client -> server direction
        key = (src_ip, src_port)
        with self._lock:
            fl = self.flows.get(key)
            if fl is None:
                fl = self.flows[key] = Flow(src_ip, src_port)
            fl.update(payload, now)

    def snapshot(self, now=None) -> list[dict]:
        """Return a feature row per live flow and reap stale ones."""
        now = now or time.time()
        with self._lock:
            items = list(self.flows.items())  # copy under lock, then release
        per_src: dict[str, int] = {}
        for (ip, _), fl in items:
            if now - fl.last_seen < self.expire_after:
                per_src[ip] = per_src.get(ip, 0) + 1
        rows = []
        dead = []
        for key, fl in items:
            if now - fl.last_seen >= self.expire_after:
                dead.append(key)
                continue
            row = fl.features(now, per_src.get(fl.src_ip, 1))
            row["src_ip"] = fl.src_ip
            row["src_port"] = fl.src_port
            rows.append(row)
        with self._lock:
            for k in dead:
                self.flows.pop(k, None)
        return rows
