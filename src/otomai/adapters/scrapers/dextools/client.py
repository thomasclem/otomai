"""
DexTools API Client - Version corrigée et optimisée
File location: src/otomai/services/dextools/client.py
"""

import json
import random
import time
from typing import Any

import requests

from .models.request import BaseRequest, PairSearchRequest
from .models.response import ApiResponse, ErrorResponse, PairSearchResponse


class DexToolsClient:
    """
    Professional DexTools API Client with comprehensive error handling and response models
    """

    def __init__(self, base_url: str = "https://www.dextools.io"):
        """
        Initialize the DexTools client

        Args:
            base_url: Base URL for the DexTools API
        """
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.base_request = BaseRequest()

        # Headers qui fonctionnent (sans compression pour éviter les données corrompues)
        self._working_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.dextools.io/",
            "Origin": "https://www.dextools.io",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

        # Set default headers (utilise les headers qui fonctionnent)
        self.session.headers.update(self._working_headers)

    def _get_working_headers(self) -> dict[str, str]:
        """
        Retourne les headers qui fonctionnent pour éviter les réponses corrompues
        """
        # Rotation des User-Agents pour éviter la détection
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]

        headers = self._working_headers.copy()
        headers["User-Agent"] = random.choice(user_agents)
        return headers

    def _make_request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> ApiResponse:
        """
        Make HTTP request with error handling and retries

        Args:
            endpoint: API endpoint
            params: Query parameters
            timeout: Request timeout

        Returns:
            ApiResponse object
        """
        url = f"{self.base_url}{endpoint}"
        timeout = timeout or self.base_request.timeout

        # Mise à jour des headers pour chaque requête
        self.session.headers.update(self._get_working_headers())

        for attempt in range(self.base_request.retry_count):
            try:
                # Délai anti-détection
                if attempt > 0:
                    time.sleep(random.uniform(1, 3))
                else:
                    time.sleep(random.uniform(0.3, 0.8))

                response = self.session.get(url, params=params, timeout=timeout)

                # Debug info pour la première tentative
                if attempt == 0:
                    print(f"🔍 Request: {response.url}")
                    print(f"📊 Status: {response.status_code}")
                    print(f"📦 Content-Type: {response.headers.get('content-type', 'N/A')}")

                # Handle successful response
                if response.status_code == 200:
                    try:
                        # Vérifier si c'est du HTML (page d'erreur)
                        content_type = response.headers.get("content-type", "").lower()
                        if "text/html" in content_type:
                            print("⚠️ HTML response detected (possible error page)")
                            if "cloudflare" in response.text.lower():
                                print("☁️ Cloudflare protection detected")
                            return ApiResponse(
                                status_code=response.status_code,
                                data=None,
                                headers=dict(response.headers),
                                url=response.url,
                                success=False,
                                error_message="HTML response received instead of JSON",
                            )

                        data = response.json() if response.content else None
                        print("✅ Successfully parsed JSON response")
                    except json.JSONDecodeError as e:
                        print(f"❌ JSON decode error: {e}")
                        print(f"📄 Response preview: {response.text[:200]}")
                        data = None

                    return ApiResponse(
                        status_code=response.status_code,
                        data=data,
                        headers=dict(response.headers),
                        url=response.url,
                    )

                # Handle error responses
                else:
                    print(f"❌ HTTP Error {response.status_code}: {response.reason}")
                    return ApiResponse(
                        status_code=response.status_code,
                        data=None,
                        headers=dict(response.headers),
                        url=response.url,
                        success=False,
                        error_message=f"HTTP {response.status_code}: {response.reason}",
                    )

            except requests.exceptions.RequestException as e:
                print(f"💥 Request exception (attempt {attempt + 1}): {e}")

                if attempt == self.base_request.retry_count - 1:
                    return ApiResponse(
                        status_code=0,
                        data=None,
                        headers={},
                        url=url,
                        success=False,
                        error_message=f"Request failed after {self.base_request.retry_count} attempts: {str(e)}",
                    )

                # Wait before retry with exponential backoff
                wait_time = self.base_request.rate_limit_delay * (2**attempt)
                print(f"⏳ Waiting {wait_time:.1f}s before retry...")
                time.sleep(wait_time)

        return ApiResponse(
            status_code=0,
            data=None,
            headers={},
            url=url,
            success=False,
            error_message="Max retries exceeded",
        )

    def search_pairs(
        self, query: str, strict: bool = True, limit: int | None = 50
    ) -> PairSearchResponse | ErrorResponse:
        """
        Search for trading pairs

        Args:
            query: Search term (token name or symbol)
            strict: Enable strict search mode
            limit: Maximum number of results

        Returns:
            PairSearchResponse or ErrorResponse
        """
        print(f"🔍 Searching pairs for: {query} (strict={strict}, limit={limit})")

        request = PairSearchRequest(query=query, strict=strict, limit=limit)
        endpoint = "/shared/search/pair"

        api_response = self._make_request(endpoint, request.to_params())

        if not api_response.success:
            return ErrorResponse(
                status_code=api_response.status_code,
                error_message=api_response.error_message,
                url=api_response.url,
                headers=api_response.headers,
            )

        try:
            if api_response.data and "results" in api_response.data:
                results = api_response.data["results"]
                print(f"✅ Found {len(results)} results")
                return PairSearchResponse(results=results)
            elif isinstance(api_response.data, list):
                print(f"✅ Found {len(api_response.data)} results (direct list)")
                return PairSearchResponse(results=api_response.data)
            else:
                print("⚠️ No results found")
                return PairSearchResponse(results=[])

        except Exception as e:
            print(f"💥 Failed to parse response: {e}")
            return ErrorResponse(
                status_code=api_response.status_code,
                error_message=f"Failed to parse response: {str(e)}",
                url=api_response.url,
                headers=api_response.headers,
            )

    def set_custom_headers(self, headers: dict[str, str]) -> None:
        """
        Set custom headers for requests

        Args:
            headers: Dictionary of headers to add/update
        """
        self._working_headers.update(headers)
        self.session.headers.update(headers)

    def set_rate_limiting(self, delay: float) -> None:
        """
        Set rate limiting delay between requests

        Args:
            delay: Delay in seconds
        """
        self.base_request.rate_limit_delay = delay

    def set_timeout(self, timeout: float) -> None:
        """
        Set request timeout

        Args:
            timeout: Timeout in seconds
        """
        self.base_request.timeout = timeout

    def set_retry_count(self, count: int) -> None:
        """
        Set number of retry attempts

        Args:
            count: Number of retries
        """
        self.base_request.retry_count = count

    def enable_debug(self, enable: bool = True) -> None:
        """
        Enable/disable debug logging

        Args:
            enable: Whether to enable debug mode
        """
        self.debug_mode = enable

    def test_connection(self) -> bool:
        """
        Test the connection to DexTools API

        Returns:
            True if connection is successful
        """
        print("🧪 Testing connection to DexTools...")
        response = self.search_pairs("test", limit=1)

        if isinstance(response, ErrorResponse):
            print(f"❌ Connection test failed: {response.error_message}")
            return False
        else:
            print("✅ Connection test successful!")
            return True

    def close(self) -> None:
        """Close the session"""
        self.session.close()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
