"""Small HTTP client for the official Technocore signed message lane."""

import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from arxiv_research_agent.technocore.identity import sign_message


_nonce_lock = threading.Lock()
_last_nonce = 0


class TechnocoreHTTPError(ValueError):
    """A safe, user-facing Technocore transport or HTTP error."""


def _safe_response_text(response: httpx.Response, limit: int = 2000) -> str:
    text = response.text.strip()
    text = " ".join(text.splitlines())
    return text[:limit] if text else "empty response body"


def next_nonce() -> str:
    global _last_nonce
    with _nonce_lock:
        current = int(time.time() * 1000)
        _last_nonce = max(current, _last_nonce + 1)
        return str(_last_nonce)


@dataclass(frozen=True)
class SignedRequest:
    url: str
    json: Dict[str, str]
    normalized_text: str


class TechnocoreClient:
    def __init__(
        self,
        base_url: str,
        room: str,
        timeout: float = 20,
        http_client: Optional[httpx.Client] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.room = room
        self.timeout = timeout
        self.http_client = http_client

    def build_signed_request(self, key: Any, text: str, nonce: Optional[str] = None) -> SignedRequest:
        actual_nonce = nonce or next_nonce()
        did, signature, normalized = sign_message(key, self.room, actual_nonce, text)
        return SignedRequest(
            url="%s/r/%s" % (self.base_url, self.room),
            json={
                "did": did,
                "sig": signature,
                "nonce": actual_nonce,
                "text": normalized,
            },
            normalized_text=normalized,
        )

    def send(self, request: SignedRequest) -> Dict[str, Any]:
        owns_client = self.http_client is None
        client = self.http_client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    request.url,
                    params={"format": "json"},
                    json=request.json,
                    headers={"Accept": "application/json"},
                )
            except httpx.HTTPError as exc:
                raise TechnocoreHTTPError(
                    "Technocore network error: %s" % exc
                ) from None
            if response.is_error:
                raise TechnocoreHTTPError(
                    "Technocore HTTP %d: %s"
                    % (response.status_code, _safe_response_text(response))
                )
            content_type = response.headers.get("content-type", "")
            if "json" in content_type:
                data = response.json()
                return data if isinstance(data, dict) else {"response": data}
            return {"response": response.text.strip()}
        finally:
            if owns_client:
                client.close()

    def read_room(self, since: Optional[int] = None, limit: int = 200) -> Dict[str, Any]:
        owns_client = self.http_client is None
        client = self.http_client or httpx.Client(timeout=self.timeout)
        params: Dict[str, Any] = {"format": "json", "limit": min(200, max(1, limit))}
        if since is not None and since > 0:
            params["since"] = int(since)
        try:
            try:
                response = client.get("%s/r/%s" % (self.base_url, self.room), params=params)
            except httpx.HTTPError as exc:
                raise TechnocoreHTTPError("Technocore network error: %s" % exc) from None
            if response.is_error:
                raise TechnocoreHTTPError(
                    "Technocore HTTP %d: %s"
                    % (response.status_code, _safe_response_text(response))
                )
            try:
                data = response.json()
            except ValueError:
                raise TechnocoreHTTPError("Technocore room response was not JSON") from None
            if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
                raise TechnocoreHTTPError("Technocore room response has an invalid shape")
            return data
        finally:
            if owns_client:
                client.close()
