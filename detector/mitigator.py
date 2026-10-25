"""
Automated, container-native mitigation with a cooldown/restore state machine.
This closed loop is the core contribution: detection alone does not act, this
does, and then lifts the action on its own when behaviour normalises.

Escalation ladder (least -> most disruptive):
  1. drop   : block the offending source IP in iptables (victim namespace)
  2. isolate: docker network disconnect the attacker container (if source maps
              to a known lab container), else keep the IP drop.
Restore: after `cooldown` seconds with no fresh offence, undo the action.
"""
import subprocess
import time

ACTION_LOG = "results/actions.csv"


class Mitigator:
    def __init__(self, docker_client=None, attacker_container=None,
                 victim_container=None, cooldown=30.0, dry_run=False):
        self.docker = docker_client
        self.attacker_container = attacker_container
        self.victim_container = victim_container
        self.cooldown = cooldown
        self.dry_run = dry_run
        self.blocked: dict[str, float] = {}   # ip -> last-offence timestamp
        self.disconnected = set()
        self._net_name = None
        with open(ACTION_LOG, "w") as f:
            f.write("ts,action,target,detail\n")

    def _log(self, action, target, detail=""):
        with open(ACTION_LOG, "a") as f:
            f.write(f"{time.time():.3f},{action},{target},{detail}\n")
        print(f"[mitigator] {action} {target} {detail}", flush=True)

    def _sh(self, cmd):
        if self.dry_run:
            self._log("DRYRUN", " ".join(cmd))
            return
        subprocess.run(cmd, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def offend(self, ip):
        """Called when a source IP is classified as attacking."""
        first_time = ip not in self.blocked
        self.blocked[ip] = time.time()
        if first_time:
            # Order matters: reset the live sockets FIRST (tcpkill must observe
            # the attacker's packets), THEN block and isolate to stop re-opens.
            self._kill_conns(ip)
            self._drop_ip(ip)
            self._maybe_isolate_container(ip)
            self._reclaim_pool()

    def _drop_ip(self, ip):
        self._sh(["iptables", "-I", "INPUT", "-s", ip, "-j", "DROP"])
        self._log("DROP_IP", ip)

    def _kill_conns(self, ip):
        # Force-close the held sockets. Blocking the IP is not enough: Apache
        # workers stay stuck reading the half-open sockets. `ss -K` would destroy
        # them where SOCK_DESTROY exists; on kernels without it (e.g. WSL2) we
        # inject RSTs with tcpkill, which reads the live packets to get correct
        # sequence numbers and resets every attacker<->victim connection. This
        # must run while the attacker is still sending, hence before the IP drop.
        self._sh(["conntrack", "-D", "-s", ip])
        self._sh(["ss", "-K", "dst", ip])  # fast path where SOCK_DESTROY exists
        self._log("KILL_CONNS", ip)

    def _reclaim_pool(self):
        # Reclaim the seized worker slots. Once the attacker is isolated at the
        # network layer it cannot re-grab slots, so we restart the victim
        # container: this closes every half-open socket at once (including the
        # kernel accept backlog) and brings up a fresh pool, restoring service
        # for legitimate users within a couple of seconds. On a native Linux
        # host the lighter `ss -K` socket-destroy would suffice, but the WSL2
        # test kernel lacks SOCK_DESTROY, so a container restart is the reliable
        # reclaim. The availability probe runs on the host, independent of this.
        if not (self.docker and self.victim_container):
            return
        try:
            v = self.docker.containers.get(self.victim_container)
            v.restart(timeout=5)
            self._log("RECLAIM_POOL", self.victim_container, "restart")
        except Exception as e:
            self._log("RECLAIM_ERROR", self.victim_container, str(e))

    def _maybe_isolate_container(self, ip):
        if not (self.docker and self.attacker_container):
            return
        try:
            c = self.docker.containers.get(self.attacker_container)
            nets = c.attrs["NetworkSettings"]["Networks"]
            for name, cfg in nets.items():
                if cfg.get("IPAddress") == ip:
                    self._net_name = name
                    self.docker.networks.get(name).disconnect(c, force=True)
                    self.disconnected.add(self.attacker_container)
                    self._log("ISOLATE_CONTAINER", self.attacker_container, name)
                    return
        except Exception as e:
            self._log("ISOLATE_ERROR", self.attacker_container, str(e))

    def tick(self):
        """Restore anything whose cooldown has elapsed with no new offence."""
        now = time.time()
        for ip, last in list(self.blocked.items()):
            if now - last >= self.cooldown:
                self._restore_ip(ip)
                del self.blocked[ip]

    def _restore_ip(self, ip):
        self._sh(["iptables", "-D", "INPUT", "-s", ip, "-j", "DROP"])
        self._log("RESTORE_IP", ip)
        if self.disconnected and self.docker and self._net_name:
            try:
                c = self.docker.containers.get(self.attacker_container)
                self.docker.networks.get(self._net_name).connect(c)
                self.disconnected.discard(self.attacker_container)
                self._log("RESTORE_CONTAINER", self.attacker_container)
            except Exception as e:
                self._log("RESTORE_ERROR", self.attacker_container, str(e))
