import typing as T

from otomai.services.database import DynamoDB
from otomai.services.exchange import BitgetExchange
from otomai.services.notifier import TelegramNotifier

NotifierServiceKind = T.Union[TelegramNotifier]

ExchangeServiceKind = T.Union[BitgetExchange]

DatabaseService = T.Union[DynamoDB]
