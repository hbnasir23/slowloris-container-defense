"""
Live packet sniffer -> FlowTable. Runs inside the victim's network namespace
(network_mode: service:victim) so it sees every connection to the service.
Emits a feature snapshot every `period` seconds to a callback.
"""
import threading
import time

from scapy.all import sniff, TCP, IP

from features import FlowTable


class Monitor:
    def __init__(self, iface="eth0", server_port=80, period=2.0):
        self.table = FlowTable(server_port=server_port)
        self.iface = iface
        self.server_port = server_port
        self.period = period
        self._stop = threading.Event()

    def _handle(self, pkt):
        if not (IP in pkt and TCP in pkt):
            return
        payload = bytes(pkt[TCP].payload)
        self.table.on_packet(
            src_ip=pkt[IP].src,
            src_port=int(pkt[TCP].sport),
            dst_port=int(pkt[TCP].dport),
            payload=payload,
        )

    def _sniff_loop(self):
        sniff(iface=self.iface, filter=f"tcp port {self.server_port}",
              prn=self._handle, store=False,
              stop_filter=lambda _: self._stop.is_set())

    def run(self, on_snapshot):
        """Start sniffing and call on_snapshot(rows, ts) every `period` s."""
        t = threading.Thread(target=self._sniff_loop, daemon=True)
        t.start()
        print(f"[monitor] sniffing {self.iface} tcp/{self.server_port}", flush=True)
        try:
            while not self._stop.is_set():
                time.sleep(self.period)
                ts = time.time()
                rows = self.table.snapshot(ts)
                on_snapshot(rows, ts)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        self._stop.set()
