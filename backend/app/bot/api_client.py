"""HTTP client the bot uses to talk to the store API.

The bot holds no business logic: every price, stock check and order rule is applied by
the API. Errors come back as ``ApiError`` with the API's Uzbek message, ready to show.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CONNECTION_PROBLEM = "Server bilan aloqa yo‘q. Birozdan so‘ng qayta urinib ko‘ring."


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


class StoreApi:
    """Thin wrapper over the API's public and customer endpoints."""

    def __init__(
        self, client: httpx.AsyncClient, *, bot_secret: str, prefix: str = "/api/v1"
    ) -> None:
        self.client = client
        self.bot_secret = bot_secret
        self.prefix = prefix

    @classmethod
    def create(cls, base_url: str, bot_secret: str) -> StoreApi:
        client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(10.0, connect=5.0),
            # The API is on the internal network; never route it through an HTTP proxy.
            trust_env=False,
        )
        return cls(client, bot_secret=bot_secret)

    async def close(self) -> None:
        await self.client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        user_id: int | None = None,
        json: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        all_headers = {"X-Bot-Secret": self.bot_secret, **(headers or {})}
        if user_id is not None:
            all_headers["X-Telegram-User-Id"] = str(user_id)
        try:
            response = await self.client.request(
                method,
                f"{self.prefix}{path}",
                json=json,
                params={k: v for k, v in (params or {}).items() if v is not None},
                headers=all_headers,
            )
        except httpx.HTTPError as exc:
            logger.warning("API request failed: %s %s: %s", method, path, exc.__class__.__name__)
            raise ApiError(0, "connection_error", CONNECTION_PROBLEM) from exc
        if response.status_code == 204:
            return None
        try:
            data = response.json()
        except ValueError:
            data = None
        if response.is_success:
            return data
        error = (data or {}).get("error") if isinstance(data, dict) else None
        if not isinstance(error, dict):
            raise ApiError(response.status_code, "http_error", CONNECTION_PROBLEM)
        raise ApiError(
            response.status_code,
            str(error.get("code", "error")),
            str(error.get("message", CONNECTION_PROBLEM)),
            error.get("details"),
        )

    # --- Public -------------------------------------------------------------------------

    async def store(self) -> dict[str, Any]:
        return await self._request("GET", "/store")

    async def categories(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/categories")

    async def products(self, **params: Any) -> dict[str, Any]:
        return await self._request("GET", "/products", params=params)

    async def product(self, product_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/products/{product_id}")

    async def regions(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/regions")

    async def districts(self, region_id: int) -> list[dict[str, Any]]:
        return await self._request("GET", f"/regions/{region_id}/districts")

    async def delivery_quotes(self, district_id: int, amount: str) -> list[dict[str, Any]]:
        return await self._request(
            "GET", "/delivery/quotes", params={"district_id": district_id, "amount": amount}
        )

    async def download(self, url: str, base_url: str | None = None) -> bytes:
        """Fetch a media file (product image) from the internal network."""
        target = f"{base_url.rstrip('/')}{url}" if base_url else url
        try:
            response = await self.client.get(target)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiError(0, "media_unavailable", "Rasmni yuklab bo‘lmadi.") from exc
        return response.content

    # --- Customer -----------------------------------------------------------------------

    async def register(
        self,
        telegram_id: int,
        first_name: str,
        last_name: str | None,
        username: str | None,
        language_code: str | None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/customers/register",
            json={
                "telegram_id": telegram_id,
                "first_name": first_name or "Mijoz",
                "last_name": last_name,
                "username": username,
                "language_code": language_code,
            },
        )

    async def set_phone(
        self, user_id: int, phone: str, contact_user_id: int | None
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/customers/phone",
            user_id=user_id,
            json={"phone": phone, "contact_user_id": contact_user_id},
        )

    async def profile(self, user_id: int) -> dict[str, Any]:
        return await self._request("GET", "/profile", user_id=user_id)

    async def addresses(self, user_id: int) -> list[dict[str, Any]]:
        return await self._request("GET", "/addresses", user_id=user_id)

    async def add_address(self, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/addresses", user_id=user_id, json=data)

    async def delete_address(self, user_id: int, address_id: str) -> None:
        await self._request("DELETE", f"/addresses/{address_id}", user_id=user_id)

    async def cart(self, user_id: int) -> dict[str, Any]:
        return await self._request("GET", "/cart", user_id=user_id)

    async def add_to_cart(self, user_id: int, variant_id: str, quantity: int = 1) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/cart/items",
            user_id=user_id,
            json={"variant_id": variant_id, "quantity": quantity},
        )

    async def set_cart_quantity(self, user_id: int, item_id: str, quantity: int) -> dict[str, Any]:
        return await self._request(
            "PATCH", f"/cart/items/{item_id}", user_id=user_id, json={"quantity": quantity}
        )

    async def clear_cart(self, user_id: int) -> None:
        await self._request("DELETE", "/cart", user_id=user_id)

    async def apply_promo(self, user_id: int, code: str) -> dict[str, Any]:
        return await self._request("POST", "/cart/promo", user_id=user_id, json={"code": code})

    async def remove_promo(self, user_id: int) -> dict[str, Any]:
        return await self._request("DELETE", "/cart/promo", user_id=user_id)

    async def checkout_preview(
        self, user_id: int, district_id: int, delivery_method_id: str
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/checkout/preview",
            user_id=user_id,
            json={"district_id": district_id, "delivery_method_id": delivery_method_id},
        )

    async def create_order(
        self, user_id: int, data: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/orders",
            user_id=user_id,
            json=data,
            headers={"Idempotency-Key": idempotency_key},
        )

    async def orders(self, user_id: int, page: int = 1, page_size: int = 5) -> dict[str, Any]:
        return await self._request(
            "GET", "/orders", user_id=user_id, params={"page": page, "page_size": page_size}
        )

    async def order(self, user_id: int, order_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/orders/{order_id}", user_id=user_id)

    async def cancel_order(self, user_id: int, order_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/orders/{order_id}/cancel", user_id=user_id, json={})

    async def start_payment(self, user_id: int, order_id: str) -> dict[str, Any]:
        return await self._request(
            "POST", "/payments", user_id=user_id, json={"order_id": order_id}
        )

    async def save_image_file_id(self, image_id: str, file_id: str) -> None:
        await self._request(
            "PUT",
            f"/bot/product-images/{image_id}/telegram-file-id",
            json={"telegram_file_id": file_id},
        )
