"""App 配对与 device_token 管理（HarBeat RK3588_API_SPEC）。"""

from __future__ import annotations

import random
import secrets
import time
from dataclasses import dataclass, field


@dataclass
class PairingStore:
  device_id: str = "rk3588-01"
  device_name: str = "RK3588-Cypher"
  pair_code: str = ""
  pair_expires_at: float = 0.0
  device_token: str | None = None
  token_expires_at: float = 0.0
  is_connected: bool = False
  last_connected_time: int = 0
  _tokens: dict[str, float] = field(default_factory=dict)

  def start_pairing(self, expires_sec: int = 120) -> str:
    self.pair_code = f"{random.randint(0, 999999):06d}"
    self.pair_expires_at = time.time() + expires_sec
    self.is_connected = False
    return self.pair_code

  def confirm(self, pair_code: str, token_ttl_sec: int = 3600) -> str | None:
    if not self.pair_code or time.time() > self.pair_expires_at:
      return None
    if pair_code.strip() != self.pair_code:
      return None
    token = secrets.token_urlsafe(32)
    self.device_token = token
    self.token_expires_at = time.time() + token_ttl_sec
    self._tokens[token] = self.token_expires_at
    self.is_connected = True
    self.last_connected_time = int(time.time())
    self.pair_code = ""
    self.pair_expires_at = 0.0
    return token

  def validate_token(self, token: str | None) -> bool:
    if not token:
      return False
    exp = self._tokens.get(token)
    if exp is None:
      if token == self.device_token and time.time() <= self.token_expires_at:
        return True
      return False
    if time.time() > exp:
      self._tokens.pop(token, None)
      return False
    return True


pairing_store = PairingStore()
