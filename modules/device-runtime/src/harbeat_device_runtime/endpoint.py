"""Safe RK endpoint normalization."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


class EndpointError(ValueError):
  """The supplied endpoint cannot be used as an RK HTTP endpoint."""


@dataclass(frozen=True, slots=True)
class RkEndpoint:
  scheme: str
  host: str
  port: int

  @classmethod
  def parse(cls, raw: str, default_port: int = 9000) -> "RkEndpoint":
    value = str(raw or "").strip()
    if not value:
      raise EndpointError("RK endpoint is empty")
    if "://" not in value:
      value = f"http://{value}"
    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
      raise EndpointError("RK endpoint must use http or https")
    if parts.username or parts.password:
      raise EndpointError("credentials must not be embedded in RK endpoint")
    if parts.path not in {"", "/"} or parts.query or parts.fragment:
      raise EndpointError("RK endpoint must contain only scheme, host, and port")
    host = parts.hostname
    if not host:
      raise EndpointError("RK endpoint host is missing")
    try:
      port = parts.port or default_port
    except ValueError as exc:
      raise EndpointError("RK endpoint port is invalid") from exc
    if not 1 <= port <= 65535:
      raise EndpointError("RK endpoint port is outside 1..65535")
    normalized_host = host.lower()
    try:
      normalized_host = ipaddress.ip_address(host).compressed
    except ValueError:
      pass
    return cls(scheme=scheme, host=normalized_host, port=port)

  @property
  def url(self) -> str:
    host = f"[{self.host}]" if ":" in self.host else self.host
    return urlunsplit((self.scheme, f"{host}:{self.port}", "", "", ""))

  @property
  def key(self) -> str:
    return self.url.lower()
