import httpx
from typing import List

from otomai.interfaces.scraper.bitget.models import GetCurrentCandyBombsResponse
from otomai.logger import Logger

logger = Logger(__name__)


class BitgetScraperClient:
    """
    Web scraper for Bitget's frontend-only features.
    """

    def __init__(self):
        self.headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.bitget.com",
            "Referer": "https://www.bitget.com/events/candy-bomb",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
        }
        self.url_candy_bomb = "https://www.bitget.com/events/candy-bomb"

    def get_current_candy_bombs(self) -> GetCurrentCandyBombsResponse:
        """
        Scrape the current Candy Bomb listed on the event page.

        Returns:
            List[str]: A list of events data (e.g., ['TANSSI', 'XYZ', ...])
        """
        payload = {}
        try:
            logger.info(f"Accessing {self.url_candy_bomb}")
            with httpx.Client() as client:
                response = client.post(
                    self.url_candy_bomb, json=payload, headers=self.headers
                )
                data = response.json().get("data")
                return GetCurrentCandyBombsResponse(**data)
        except Exception as e:
            logger.error(f"Fail to access {self.url_candy_bomb}: {e}")
            raise

    def get_current_candy_bomb_symbols(self) -> List[str]:
        current_candy_bombs_data: GetCurrentCandyBombsResponse = (
            self.get_current_candy_bombs()
        )
        return [
            processing_activity.name
            for processing_activity in current_candy_bombs_data.processingActivities
        ]
