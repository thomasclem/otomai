"""
DexTools API Request Models
File location: src/otomai/services/dextools/models/request.py
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum
from fake_useragent import UserAgent
import random


class ChainType(Enum):
    """Supported blockchain networks"""

    ETHEREUM = "ether"
    BSC = "bsc"
    POLYGON = "polygon"
    AVALANCHE = "avalanche"
    FANTOM = "fantom"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"


class PairSearchStrictMode(Enum):
    """Search strictness modes"""

    STRICT = True
    LOOSE = False


@dataclass
class PairSearchRequest:
    """Request payload for pair search endpoint"""

    query: str
    strict: bool = True
    limit: Optional[int] = 50

    def to_params(self) -> Dict[str, Any]:
        """Convert to URL parameters"""
        params = {"query": self.query, "strict": str(self.strict).lower()}
        if self.limit:
            params["limit"] = self.limit
        return params


@dataclass
class BaseRequest:
    """Base request configuration"""

    timeout: float = 30.0
    retry_count: int = 3
    rate_limit_delay: float = 1.0
    ua: UserAgent = field(default_factory=UserAgent)

    def get_headers(self) -> Dict[str, str]:
        """Get default headers for requests"""
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0",
        ]

        return {
            "User-Agent": random.choice(user_agents),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.dextools.io/",
            "Origin": "https://www.dextools.io",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Sec-CH-UA": '"Google Chrome";v="91", "Chromium";v="91", ";Not A Brand";v="99"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

    def get_session_headers(self) -> Dict[str, str]:
        """Get headers with session-like behavior"""
        base_headers = self.get_headers()

        # Add some randomization to make requests look more natural
        if random.random() > 0.5:
            base_headers["DNT"] = "1"

        if random.random() > 0.3:
            base_headers["Upgrade-Insecure-Requests"] = "1"

        return base_headers


@dataclass
class RequestConfig:
    """Complete request configuration"""

    base_request: BaseRequest = field(default_factory=BaseRequest)
    use_session: bool = True
    verify_ssl: bool = True

    def get_request_kwargs(self) -> Dict[str, Any]:
        """Get complete request configuration"""
        kwargs = {
            "timeout": self.base_request.timeout,
            "headers": self.base_request.get_session_headers(),
            "verify": self.verify_ssl,
        }

        return kwargs
