import abc
import os
import typing as T

import boto3
import pydantic as pdt
from pydantic import PrivateAttr
from sqlmodel import Session, SQLModel, create_engine, select

from otomai.core.models import Trade, Trades
from otomai.logger import Logger

logger = Logger(__name__)


class DataBase(abc.ABC, pdt.BaseModel):
    KIND: str

    @abc.abstractmethod
    def create_table(self):
        """
        Abstract method to create table.
        """
        pass

    @abc.abstractmethod
    def insert_trade(self, trade: Trade):
        """
        Abstract method to insert trade to database. Must be implemented by subclasses.
        """
        pass

    @abc.abstractmethod
    def fetch_all_trades(self) -> Trades:
        """
        Abstract method to fetch all trades from database. Must be implemented by subclasses.
        """
        pass


class SQLiteDB(DataBase):
    KIND: T.Literal["SQLite"] = "SQLite"
    db_url: str = pdt.Field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///data/otomai.db"))

    _engine: T.Any = PrivateAttr()

    def __init__(self, **data):
        super().__init__(**data)
        self.__post_init__()

    def __post_init__(self):
        # Ensure the directory exists
        if self.db_url.startswith("sqlite:///"):
            path = self.db_url.replace("sqlite:///", "")
            if "/" in path:
                os.makedirs(os.path.dirname(path), exist_ok=True)
        
        self._engine = create_engine(self.db_url)

    def create_table(self):
        try:
            SQLModel.metadata.create_all(self._engine)
            logger.info("Tables created successfully (if they didn't exist).")
        except Exception as e:
            logger.error(f"Error creating tables: {e}")

    def insert_trade(self, trade: Trade):
        logger.info(f"Saving trade {trade.id} to SQLite database...")
        try:
            with Session(self._engine) as session:
                session.add(trade)
                session.commit()
                session.refresh(trade)
            logger.info("Trade saved successfully")
        except Exception as e:
            logger.error(f"Trade saving failed: {e}")
            raise

    def fetch_all_trades(self) -> Trades:
        try:
            with Session(self._engine) as session:
                statement = select(Trade)
                results = session.exec(statement).all()
                return Trades(trades=list(results))
        except Exception as e:
            logger.error(f"Error fetching all trades: {e}")
            return Trades(trades=[])


class DynamoDB(DataBase):
    KIND: T.Literal["DynamoDB"] = "DynamoDB"

    aws_access_key_id: str = pdt.Field(
        default_factory=lambda: os.getenv("AWS_ACCESS_KEY_ID")
    )
    aws_secret_access_key: str = pdt.Field(
        default_factory=lambda: os.getenv("AWS_SECRET_ACCESS_KEY")
    )
    region_name: str = pdt.Field(default_factory=lambda: os.getenv("AWS_REGION_NAME"))
    table_name: str = pdt.Field(default_factory=lambda: f"{os.getenv('ENV')}_trades")

    _session: boto3.Session = PrivateAttr()
    _dynamodb: T.Any = PrivateAttr()
    _table: T.Any = PrivateAttr()

    def __init__(self, **data):
        super().__init__(**data)
        self.__post_init__()

    def __post_init__(self, **kwargs):
        """Post-initialization to set up AWS resources."""
        self._session = boto3.Session(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.region_name,
        )
        self._dynamodb = self._session.resource("dynamodb")
        self._table = self._dynamodb.Table(self.table_name)

    def create_table(self):
        try:
            self._table = self._dynamodb.create_table(
                TableName=self.table_name,
                KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
                ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
            )
            self._table.wait_until_exists()
            print(f"Table {self.table_name} created successfully")
        except Exception as e:
            # Check if it's just "ResourceInUseException" (table exists)
            print(f"Error creating table (might already exist): {e}")

    def insert_trade(self, trade: Trade):
        logger.info("Saving trade to DynamoDB...")
        try:
            # DynamoDB requires dict, not SQLModel object directly usually, 
            # and clean out incompatible types if any. 
            # trade.model_dump() should work for Pydantic/SQLModel
            item = trade.model_dump(mode='json')
            # Remove None values as DynamoDB doesn't like them sometimes or just to save space
            item = {k: v for k, v in item.items() if v is not None}
            self._table.put_item(Item=item)
            logger.info("Trade saved successfully")
        except Exception as e:
            logger.error(f"Trade saving failed: {e}")
            raise

    def fetch_all_trades(self) -> Trades:
        try:
            response = self._table.scan()
            items = response.get("Items", [])
            # Convert back to Trade objects
            trades = [Trade(**item) for item in items]
            return Trades(trades=trades)
        except Exception as e:
            logger.error(f"Error fetching all trades: {e}")
            return Trades(trades=[])
