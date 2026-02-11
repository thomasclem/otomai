
import abc
import os
import typing as T

import boto3
import pydantic as pdt
from pydantic import PrivateAttr
from sqlmodel import Session, SQLModel, create_engine, select

from otomai.logger import Logger
from otomai.core.models import Trade, Trades

logger = Logger(__name__)


class DatabaseService(abc.ABC, pdt.BaseModel):
    KIND: str

    @abc.abstractmethod
    def insert_trade(self, trade: Trade):
        """
        Abstract method to insert trade to database. Must be implemented by subclasses.
        """
        pass

    @abc.abstractmethod
    def fetch_all_trades(self):
        """
        Abstract method to fetch all trades from database. Must be implemented by subclasses.
        """
        pass


class DynamoDB(DatabaseService):
    KIND: T.Literal["DynamoDB"] = "DynamoDB"

    aws_access_key_id: str = pdt.Field(
        default_factory=lambda: os.getenv("AWS_ACCESS_KEY_ID")
    )
    aws_secret_access_key: str = pdt.Field(
        default_factory=lambda: os.getenv("AWS_SECRET_ACCESS_KEY")
    )
    region_name: str = pdt.Field(default_factory=lambda: os.getenv("AWS_REGION"))
    table_name: str = pdt.Field(default_factory=lambda: f"{os.getenv('ENV')}_trades")

    _session: boto3.Session = PrivateAttr()
    _dynamodb: T.Any = PrivateAttr()
    _table: T.Any = PrivateAttr()

    def __init__(self, **data):
        super().__init__(**data)
        self.__post_init__()

    def __post_init__(self, **kwargs):
        """Post-initialization to set up AWS resources."""
        # Only initialize if AWS keys are present, or handle gracefully?
        # Assuming user responsible for env vars if they choose DynamoDB.
        if self.aws_access_key_id and self.aws_secret_access_key:
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
                AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}], # Trade ID is string (UUID)
                ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
            )
            self._table.meta.client.get_waiter("table_exists").wait(
                TableName=self.table_name
            )
            print(f"Table {self.table_name} created successfully")
        except Exception as e:
            print(f"Error creating table: {e}")

    def insert_trade(self, trade: Trade):
        logger.info("Saving trade to DynamoDB...")
        try:
            # SQLModel/Pydantic v2 dump
            item = trade.model_dump()
            # Remove None values for DynamoDB
            item = {k: v for k, v in item.items() if v is not None}
            self._table.put_item(Item=item)
            logger.info("Trade saved successfully to DynamoDB")
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


class SQLiteDB(DatabaseService):
    KIND: T.Literal["SQLiteDB"] = "SQLiteDB"
    
    db_url: str = pdt.Field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///data/otomai.db"))
    
    _engine: T.Any = PrivateAttr()

    def __init__(self, **data):
        super().__init__(**data)
        self.__post_init__()

    def __post_init__(self, **kwargs):
        """Post-initialization to set up SQLite resources."""
        # Ensure data directory exists if using local file
        if self.db_url.startswith("sqlite:///"):
            path = self.db_url.replace("sqlite:///", "")
            directory = os.path.dirname(path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                
        self._engine = create_engine(self.db_url)
        self.create_tables()

    def create_tables(self):
        try:
            SQLModel.metadata.create_all(self._engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating tables: {e}")

    def insert_trade(self, trade: Trade):
        logger.info("Saving trade to SQLite...")
        try:
            with Session(self._engine) as session:
                session.add(trade)
                session.commit()
                session.refresh(trade)
            logger.info("Trade saved successfully to SQLite")
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
