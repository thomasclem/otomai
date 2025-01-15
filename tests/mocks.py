from otomai.services.exchange import BitgetExchange
from otomai.services.notifier import TelegramNotifier

from otomai.services.database import DynamoDB


class MockExchange(BitgetExchange):
    def __init__(self):
        super().__init__(KIND="Bitget")


class MockNotifier(TelegramNotifier):
    def __init__(self):
        super().__init__(KIND="Telegram", chat_id="test_chat_id")


class MockDatabase(DynamoDB):
    def __init__(self):
        super().__init__()
