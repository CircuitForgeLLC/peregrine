# scripts/safe_net.py
"""
Outbound networking that cannot be aimed at the internal network (peregrine#228, #250).

On the hosted version the API container can reach services a tenant must never reach: the other
containers, the orchestrator, the host, cloud metadata endpoints. Any request built from an address
a tenant typed (a webhook URL, a job link, a mail server) goes through here instead of straight to
`requests`:

  - The name is resolved once with getaddrinfo, IPv4 and IPv6 together, and the request is refused
    if ANY returned address is not a public one. Private, loopback, link-local, carrier-grade NAT,
    unique-local, multicast, reserved, documentation and metadata ranges are all refused, and so are
    IPv4-in-IPv6 forms (mapped, 6to4, Teredo, NAT64) that hide one.
  - The connection is then made to the address that was checked. There is no second lookup, so a
    name that answers differently the second time (DNS rebinding) cannot change where it goes. The
    hostname is still used for the TLS check and the Host header.
  - Redirects are followed at most three times, every hop is connected through the same checks, and a
    hop that would drop from https to http is refused.

Self-hosted installs are not restricted: a LAN Home Assistant or a local Nextcloud is legitimate
there. `http_session()` returns the safe session only when CLOUD_MODE is on.
"""
import imaplib
import ipaddress
import os
import socket
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError, NewConnectionError
from urllib3.poolmanager import PoolManager

MAX_REDIRECTS = 3

_BLOCKED_NETWORKS = [ipaddress.ip_network(net) for net in (
    # IPv4
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
    "192.0.0.0/24", "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24",
    "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4",
    # IPv6
    "::/128", "::1/128", "64:ff9b::/96", "64:ff9b:1::/48", "100::/64", "2001::/32", "2001:db8::/32",
    "2002::/16", "fc00::/7", "fe80::/10", "fec0::/10", "ff00::/8",
)]


class BlockedAddress(OSError):
    """The host is not a public address, cannot be resolved, or is not a plain host name."""


class BlockedRedirect(requests.RequestException):
    """A redirect that would leave https was refused."""


def cloud_mode() -> bool:
    return os.environ.get("CLOUD_MODE", "").strip().lower() in {"1", "true", "yes"}


def is_public_ip(value) -> bool:
    """True only for an address that is routable on the public internet."""
    try:
        addr = ipaddress.ip_address(str(value).strip().split("%", 1)[0])
    except ValueError:
        return False
    if addr.version == 6 and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    if any(addr in net for net in _BLOCKED_NETWORKS):
        return False
    return addr.is_global and not (
        addr.is_private or addr.is_loopback or addr.is_link_local
        or addr.is_multicast or addr.is_reserved or addr.is_unspecified
    )


def resolve_public(host: str, port: int) -> list[str]:
    """Resolve host once and return its addresses, or raise BlockedAddress.

    Every address getaddrinfo returns must be public, so a name that mixes a public address with an
    internal one is refused outright rather than tried in order.
    """
    name = (host or "").strip().rstrip(".")
    if not name or any(ch in name for ch in " \t\r\n/\\@?#"):
        raise BlockedAddress("not a plain host name")
    try:
        infos = socket.getaddrinfo(name, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as exc:
        raise BlockedAddress("host could not be resolved") from exc
    addresses: list[str] = []
    for info in infos:
        ip = info[4][0].split("%", 1)[0]
        if not is_public_ip(ip):
            raise BlockedAddress("host resolves to a non-public address")
        if ip not in addresses:
            addresses.append(ip)
    if not addresses:
        raise BlockedAddress("host did not resolve to any address")
    return addresses


def create_connection(address: tuple[str, int], timeout: float | None = None) -> socket.socket:
    """socket.create_connection, but to a vetted address and after one lookup only.

    timeout=None means no timeout, so callers should pass one.
    """
    host, port = address
    last_error: OSError | None = None
    for ip in resolve_public(host, port):
        try:
            return socket.create_connection((ip, port), timeout)
        except OSError as exc:
            last_error = exc
    raise last_error or BlockedAddress("no address to connect to")


def public_url_error(url: str, schemes: tuple[str, ...] = ("https",)) -> str | None:
    """Why an address typed by a user must not be requested, or None if it is fine.

    Meant for refusing a bad address when it is saved. The connection itself is still checked again
    by the safe session, because a check here cannot see what a name resolves to later.
    """
    text = (url or "").strip()
    if not text:
        return "empty"
    try:
        parsed = urlparse(text)
        host, port = parsed.hostname, parsed.port
    except ValueError:
        return "malformed"
    if parsed.scheme not in schemes or not host:
        return "scheme or host"
    if parsed.username or parsed.password:
        return "credentials in the address"
    try:
        resolve_public(host, port or (443 if parsed.scheme == "https" else 80))
    except BlockedAddress:
        return "not a public address"
    return None


class _PinnedConnection:
    """Mixin for urllib3 connections: connect to a checked address, never to a second lookup.

    urllib3 resolves `_dns_host` inside `_new_conn`. Swap in each vetted IP for the duration of the
    connect, so nothing is resolved again. `host` is untouched, so SNI, certificate checks and the
    Host header still use the name.
    """

    def _new_conn(self):
        dns_host = getattr(self, "_dns_host", None)
        if dns_host is None:
            raise BlockedAddress("urllib3 internals changed, refusing to connect without pinning")
        last_error = None
        for ip in resolve_public(dns_host, self.port):
            self._dns_host = ip
            try:
                return super()._new_conn()
            except (NewConnectionError, ConnectTimeoutError) as exc:
                last_error = exc
            finally:
                self._dns_host = dns_host
        raise last_error  # resolve_public never returns an empty list


class _SafeHTTPConnection(_PinnedConnection, HTTPConnection):
    pass


class _SafeHTTPSConnection(_PinnedConnection, HTTPSConnection):
    pass


class _SafeHTTPConnectionPool(HTTPConnectionPool):
    ConnectionCls = _SafeHTTPConnection


class _SafeHTTPSConnectionPool(HTTPSConnectionPool):
    ConnectionCls = _SafeHTTPSConnection


class _SafePoolManager(PoolManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pool_classes_by_scheme = {"http": _SafeHTTPConnectionPool, "https": _SafeHTTPSConnectionPool}


class _SafeAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        self._pool_connections = connections
        self._pool_maxsize = maxsize
        self._pool_block = block
        self.poolmanager = _SafePoolManager(num_pools=connections, maxsize=maxsize, block=block, **pool_kwargs)

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        raise requests.exceptions.ProxyError("Proxies are not allowed for user-supplied addresses.")


class SafeSession(requests.Session):
    """A requests session whose every connection, redirects included, goes through the checks above."""

    def __init__(self):
        super().__init__()
        self.trust_env = False  # environment proxies would let a request bypass the pinned connection
        self.max_redirects = MAX_REDIRECTS
        adapter = _SafeAdapter(max_retries=0)
        self.mount("https://", adapter)
        self.mount("http://", adapter)

    def get_redirect_target(self, resp):
        target = super().get_redirect_target(resp)
        if target and urlparse(urljoin(resp.url, target)).scheme != "https":
            raise BlockedRedirect("Refusing a redirect to a non-https address.")
        return target


def http_session() -> requests.Session:
    """The safe session on the hosted version, an ordinary one on a self-hosted install."""
    return SafeSession() if cloud_mode() else requests.Session()


class PinnedIMAP4(imaplib.IMAP4):
    """imaplib connects by host name and so resolves it itself. This connects to a checked address."""

    def _create_socket(self, timeout):
        return create_connection((self.host, self.port), timeout)


class PinnedIMAP4_SSL(imaplib.IMAP4_SSL):
    """TLS over a checked address, still verified against the host name that was typed."""

    def _create_socket(self, timeout):
        sock = create_connection((self.host, self.port), timeout)
        return self.ssl_context.wrap_socket(sock, server_hostname=self.host)
