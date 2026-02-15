import typing as T

from otomai.services.database import SQLiteDB, DynamoDB
from otomai.services.exchange import BitgetExchange
from otomai.services.notifier import TelegramNotifier

NotifierService = T.Union[TelegramNotifier]

ExchangeServiceKind = T.Union[BitgetExchange]

DatabaseService = T.Union[SQLiteDB, DynamoDB]
