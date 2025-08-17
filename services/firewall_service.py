import logging
import subprocess
import re
from typing import Optional, Set, Tuple, Dict
from datetime import datetime
from django.http import HttpRequest

logger = logging.getLogger(__name__)


class FirewallService:
    NFTABLES_TABLE = "xctf"
    NFTABLES_CHAIN = "sandbox_access"
    NFTABLES_MAP = "sandbox_port_to_ip"
    NFTABLES_STATIC_PORTS_SET = "static_ports"
    NFTABLES_SANDBOX_PORTS_SET = "sandbox_ports"
    NFTABLES_RULES_FILE = "/etc/nftables/xctf-rules.conf"
    ERROR_PAGE_PORT = 5000
    PORT_IP_SET_PREFIX = "sandbox_port_"
    SANDBOX_PORT_RANGE = "32768-65535"

    def __init__(self) -> None:
        self._initialized = False

    def _run_nftables_command(
        self, command: str, check: bool = True
    ) -> Tuple[bool, str]:
        try:
            pattern = r"\{[^}]*\}|\S+"
            tokens = re.findall(pattern, command)
            cmd_parts = ["sudo", "nft"] + tokens
            result = subprocess.run(
                cmd_parts, shell=False, capture_output=True, text=True, timeout=10
            )

            if result.returncode != 0:
                error_msg = (
                    result.stderr.strip() if result.stderr else result.stdout.strip()
                )
                if check:
                    logger.error(
                        f"Nftables command failed: {command}, error: {error_msg}"
                    )
                    raise RuntimeError(f"Nftables command failed: {error_msg}")
                else:
                    if (
                        "not found" in error_msg.lower()
                        or "does not exist" in error_msg.lower()
                    ):
                        logger.debug(
                            f"Nftables element not found (expected): {command}, error: {error_msg}"
                        )
                    else:
                        logger.warning(
                            f"Nftables command failed (non-critical): {command}, error: {error_msg}"
                        )
                return False, error_msg

            return True, result.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.error(f"Nftables command timed out: {command}", exc_info=True)
            if check:
                raise RuntimeError("Nftables command timed out")
            return False, "Command timed out"
        except Exception:
            logger.error(f"Error running nftables command: {command}", exc_info=True)
            if check:
                raise
            return False, f"Error running nftables command: {command}"

    def initialize_firewall(self) -> bool:
        if self._initialized:
            return True

        try:
            success, _ = self._run_nftables_command("list table inet xctf", check=False)
            if success:
                logger.info("Nftables table 'xctf' already exists")
                self._initialized = True
                return True

            self._run_nftables_command("add table inet xctf")
            logger.info("Created nftables table 'xctf'")

            self._run_nftables_command(
                f"add map inet xctf {self.NFTABLES_MAP} {{ "
                f"type inet_service . ipv4_addr : verdict; }}"
            )
            logger.info(f"Created nftables map '{self.NFTABLES_MAP}'")

            self._run_nftables_command(
                f"add set inet xctf {self.NFTABLES_STATIC_PORTS_SET} {{ "
                f"type inet_service; flags interval; }}"
            )
            logger.info(f"Created nftables set '{self.NFTABLES_STATIC_PORTS_SET}'")

            self._run_nftables_command(
                f"add set inet xctf {self.NFTABLES_SANDBOX_PORTS_SET} {{ "
                f"type inet_service; flags interval; }}"
            )
            logger.info(f"Created nftables set '{self.NFTABLES_SANDBOX_PORTS_SET}'")

            prerouting_chain = f"{self.NFTABLES_CHAIN}_prerouting"
            self._run_nftables_command(
                f"add chain inet xctf {prerouting_chain} {{ type filter hook prerouting priority -300; policy accept; }}"
            )
            logger.info(
                f"Created nftables prerouting chain '{prerouting_chain}' with priority -300 (before NAT)"
            )

            self._run_nftables_command(
                f"add rule inet xctf {prerouting_chain} "
                f"tcp dport != @{self.NFTABLES_SANDBOX_PORTS_SET} "
                f"counter accept"
            )

            self._run_nftables_command(
                f"add rule inet xctf {prerouting_chain} "
                f"tcp dport @{self.NFTABLES_STATIC_PORTS_SET} "
                f'counter log prefix "[XCTF-PREROUTING-STATIC] " accept'
            )

            self._run_nftables_command(
                f"add rule inet xctf {prerouting_chain} "
                f"tcp dport @{self.NFTABLES_SANDBOX_PORTS_SET} "
                f"tcp dport != @{self.NFTABLES_STATIC_PORTS_SET} "
                f"counter tcp dport . ip saddr vmap @{self.NFTABLES_MAP}"
            )

            self._run_nftables_command(
                f"add rule inet xctf {prerouting_chain} "
                f"tcp dport @{self.NFTABLES_SANDBOX_PORTS_SET} "
                f"tcp dport != @{self.NFTABLES_STATIC_PORTS_SET} "
                f'counter log prefix "[XCTF-PREROUTING-REJECT] " reject with tcp reset'
            )

            self._run_nftables_command(
                f"add chain inet xctf {self.NFTABLES_CHAIN} {{ type filter hook input priority -100; policy accept; }}"
            )
            logger.info(
                f"Created nftables chain '{self.NFTABLES_CHAIN}' with priority -100 (before iptables)"
            )

            self._run_nftables_command(
                f"add rule inet xctf {self.NFTABLES_CHAIN} "
                f"tcp dport != @{self.NFTABLES_SANDBOX_PORTS_SET} "
                f'counter log prefix "[XCTF-ACCEPT-NON-SANDBOX] " accept'
            )

            self._run_nftables_command(
                f"add rule inet xctf {self.NFTABLES_CHAIN} "
                f"tcp dport @{self.NFTABLES_STATIC_PORTS_SET} "
                f'counter log prefix "[XCTF-ACCEPT-STATIC] " accept'
            )

            self._run_nftables_command(
                f"add rule inet xctf {self.NFTABLES_CHAIN} "
                f"tcp dport @{self.NFTABLES_SANDBOX_PORTS_SET} "
                f"tcp dport != @{self.NFTABLES_STATIC_PORTS_SET} "
                f"counter tcp dport . ip saddr vmap @{self.NFTABLES_MAP}"
            )

            self._run_nftables_command(
                f"add rule inet xctf {self.NFTABLES_CHAIN} "
                f"tcp dport @{self.NFTABLES_SANDBOX_PORTS_SET} "
                f"tcp dport != @{self.NFTABLES_STATIC_PORTS_SET} "
                f'counter log prefix "[XCTF-REJECT] " reject with tcp reset'
            )

            logger.info("Nftables firewall initialized successfully")
            self._initialized = True
            return True

        except Exception:
            logger.error("Failed to initialize nftables firewall", exc_info=True)
            raise

    def add_port_ip_mapping(self, port: int, ip_address: str) -> bool:
        try:
            if not self._initialized:
                self.initialize_firewall()

            result = self._run_nftables_command(
                f"add element inet xctf {self.NFTABLES_SANDBOX_PORTS_SET} {{ {port} }}",
                check=False,
            )
            if not result[0]:
                logger.warning(
                    f"Failed to add port {port} to sandbox_ports set: {result[1]}"
                )
            else:
                logger.info(f"Added port {port} to sandbox_ports set")

            result = self._run_nftables_command(
                f"add element inet xctf {self.NFTABLES_MAP} {{ {port} . {ip_address} : accept }}"
            )
            if not result[0]:
                logger.error(f"Failed to add to map: {result[1]}")
                return False
            logger.info(f"Added firewall rule: port {port}, IP {ip_address} -> accept")
            return True

        except Exception:
            logger.error(
                f"Failed to add port-to-IP mapping: port={port}, ip={ip_address}",
                exc_info=True,
            )
            return False

    def clean_orphan_ports(self, active_ports: Set[int]) -> bool:
        try:
            if not self._initialized:
                logger.warning("Firewall not initialized, cannot clean orphan ports")
                return False

            success, output = self._run_nftables_command(
                f"list set inet xctf {self.NFTABLES_SANDBOX_PORTS_SET}", check=False
            )

            if not success:
                logger.warning(f"Failed to list sandbox_ports set: {output}")
                return False

            current_ports = set()
            elements_match = re.search(r"elements\s*=\s*\{([^}]+)\}", output)
            if elements_match:
                elements_str = elements_match.group(1)
                port_pattern = r"(\d+)(?:-(\d+))?"
                matches = re.findall(port_pattern, elements_str)
                for match in matches:
                    try:
                        start_port = int(match[0])
                        end_port = int(match[1]) if match[1] else start_port
                        for port in range(start_port, end_port + 1):
                            if 32768 <= port <= 65535:
                                current_ports.add(port)
                    except (ValueError, IndexError, TypeError):
                        pass

            orphan_ports = current_ports - active_ports

            if not orphan_ports:
                logger.info("No orphan ports found in firewall")
                return True

            logger.info(
                f"Found {len(orphan_ports)} orphan ports to clean: {orphan_ports}"
            )

            cleaned_count = 0
            for port in orphan_ports:
                try:
                    self._run_nftables_command(
                        f"delete element inet xctf {self.NFTABLES_SANDBOX_PORTS_SET} {{ {port} }}",
                        check=False,
                    )

                    self._run_nftables_command(
                        f"delete element inet xctf {self.NFTABLES_STATIC_PORTS_SET} {{ {port} }}",
                        check=False,
                    )

                    map_success, map_output = self._run_nftables_command(
                        f"list map inet xctf {self.NFTABLES_MAP}", check=False
                    )

                    if map_success:
                        map_pattern = (
                            rf"\b{port}\s+\.\s+(\d+\.\d+\.\d+\.\d+)\s+:\s+accept"
                        )
                        ip_matches = re.findall(map_pattern, map_output)
                        for ip in ip_matches:
                            self._run_nftables_command(
                                f"delete element inet xctf {self.NFTABLES_MAP} {{ {port} . {ip} : accept }}",
                                check=False,
                            )
                            logger.debug(f"Removed map entry: {port} . {ip}")

                    cleaned_count += 1
                    logger.info(f"Cleaned orphan port: {port}")

                except Exception:
                    logger.error(f"Error cleaning orphan port {port}", exc_info=True)
                    continue

            logger.info(
                f"Successfully cleaned {cleaned_count}/{len(orphan_ports)} orphan ports"
            )
            return True

        except Exception:
            logger.error("Failed to clean orphan ports", exc_info=True)
            return False

    def remove_port_ip_mapping(self, port: int, ip_address: str) -> bool:
        try:
            if not self._initialized:
                logger.warning("Firewall not initialized, cannot remove mapping")
                return False

            self._run_nftables_command(
                f"delete element inet xctf {self.NFTABLES_MAP} {{ {port} . {ip_address} : accept }}",
                check=False,
            )

            logger.info(f"Removed firewall rule: port {port}, IP {ip_address}")
            return True

        except Exception:
            logger.error(
                f"Failed to remove port-to-IP mapping: port={port}, ip={ip_address}",
                exc_info=True,
            )
            return False

    def add_static_port(self, port: int) -> bool:
        try:
            if not self._initialized:
                self.initialize_firewall()

            self._run_nftables_command(
                f"add element inet xctf {self.NFTABLES_STATIC_PORTS_SET} {{ {port} }}"
            )
            logger.info(f"Added static port {port} to firewall allowlist")
            return True

        except Exception:
            logger.error(f"Failed to add static port: port={port}", exc_info=True)
            return False

    def remove_static_port(self, port: int) -> bool:
        try:
            if not self._initialized:
                logger.warning("Firewall not initialized, cannot remove static port")
                return False

            self._run_nftables_command(
                f"delete element inet xctf {self.NFTABLES_STATIC_PORTS_SET} {{ {port} }}",
                check=False,
            )
            logger.info(f"Removed static port {port} from firewall allowlist")
            return True

        except Exception:
            logger.error(f"Failed to remove static port: port={port}", exc_info=True)
            return False

    def remove_sandbox_port(self, port: int) -> bool:
        try:
            if not self._initialized:
                logger.warning("Firewall not initialized, cannot remove sandbox port")
                return False

            self._run_nftables_command(
                f"delete element inet xctf {self.NFTABLES_SANDBOX_PORTS_SET} {{ {port} }}",
                check=False,
            )
            logger.info(f"Removed port {port} from sandbox_ports set")
            return True

        except Exception:
            logger.error(f"Failed to remove sandbox port: port={port}", exc_info=True)
            return False

    def remove_all_ports_for_ip(self, ip_address: str) -> bool:
        try:
            if not self._initialized:
                logger.warning("Firewall not initialized, cannot remove IP mappings")
                return False

            logger.info(f"Removed all firewall rules for IP {ip_address}")
            return True

        except Exception:
            logger.error(
                f"Failed to remove all ports for IP: ip={ip_address}", exc_info=True
            )
            return False

    def remove_all_port_mappings_for_sandbox(
        self, sandbox_port: int, port_mappings: Optional[Dict[str, int]] = None
    ) -> bool:
        try:
            if not self._initialized:
                logger.warning(
                    "Firewall not initialized, cannot remove sandbox mappings"
                )
                return False

            ports_to_clean = [sandbox_port]
            if port_mappings:
                for port in port_mappings.values():
                    if isinstance(port, (int, str)):
                        try:
                            port_int = int(port)
                            if port_int not in ports_to_clean:
                                ports_to_clean.append(port_int)
                        except (ValueError, TypeError):
                            pass

            map_success, map_output = self._run_nftables_command(
                f"list map inet xctf {self.NFTABLES_MAP}", check=False
            )

            cleaned_count = 0
            for port in ports_to_clean:
                self._run_nftables_command(
                    f"delete element inet xctf {self.NFTABLES_SANDBOX_PORTS_SET} {{ {port} }}",
                    check=False,
                )

                self._run_nftables_command(
                    f"delete element inet xctf {self.NFTABLES_STATIC_PORTS_SET} {{ {port} }}",
                    check=False,
                )

                if map_success:
                    map_pattern = rf"\b{port}\s+\.\s+(\d+\.\d+\.\d+\.\d+)\s+:\s+accept"
                    ip_matches = re.findall(map_pattern, map_output)
                    for ip in ip_matches:
                        self._run_nftables_command(
                            f"delete element inet xctf {self.NFTABLES_MAP} {{ {port} . {ip} : accept }}",
                            check=False,
                        )
                        logger.debug(f"Removed map entry: {port} . {ip}")
                        cleaned_count += 1

            logger.info(
                f"Removed all firewall rules for sandbox ports: {ports_to_clean}, cleaned {cleaned_count} mappings"
            )
            return True

        except Exception:
            logger.error(
                f"Failed to remove all port mappings for sandbox: port={sandbox_port}",
                exc_info=True,
            )
            return False

    def get_client_ip(self, request: HttpRequest) -> str:
        x_forwarded_for: str = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if x_forwarded_for:
            ips = [ip.strip() for ip in x_forwarded_for.split(",")]
            if ips and ips[0]:
                return ips[0]

        x_real_ip: str = request.META.get("HTTP_X_REAL_IP", "")
        if x_real_ip:
            return x_real_ip.strip()

        remote_addr: str = request.META.get("REMOTE_ADDR", "")
        if remote_addr:
            return remote_addr

        return "0.0.0.0"

    def save_rules_to_file(self) -> bool:
        try:
            success, output = self._run_nftables_command("list table inet xctf")
            if not success:
                return False

            with open(self.NFTABLES_RULES_FILE, "w") as f:
                f.write("# X-CTF Firewall Rules\n")
                f.write(f"# Generated at {datetime.now().isoformat()}\n\n")
                f.write(output)

            logger.info(f"Saved nftables rules to {self.NFTABLES_RULES_FILE}")
            return True

        except Exception:
            logger.error("Failed to save nftables rules to file", exc_info=True)
            return False


_firewall_service: Optional[FirewallService] = None


def get_firewall_service() -> FirewallService:
    global _firewall_service
    if _firewall_service is None:
        _firewall_service = FirewallService()
    return _firewall_service
