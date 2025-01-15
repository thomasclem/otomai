import abc
import os
import typing as T

import boto3
import pydantic as pdt
from pydantic import PrivateAttr

from otomai.logger import Logger
from otomai.core.models import Position, Positions

logger = Logger(__name__)


class DataBase(abc.ABC, pdt.BaseModel):
    KIND: str

    @abc.abstractmethod
    def insert_position(self, position: Position):
        """
        Abstract method to insert position to database. Must be implemented by subclasses.
        """
        pass

    @abc.abstractmethod
    def fetch_all_positions(self):
        """
        Abstract method to fetch all positions from database. Must be implemented by subclasses.
        """
        pass


class DynamoDB(DataBase):
    KIND: T.Literal["DynamoDB"] = "DynamoDB"

    aws_access_key_id: str = pdt.Field(default_factory=lambda: os.getenv("AWS_ACCESS_KEY_ID"))
    aws_secret_access_key: str = pdt.Field(default_factory=lambda: os.getenv("AWS_SECRET_ACCESS_KEY"))
    region_name: str = pdt.Field(default_factory=lambda: os.getenv("AWS_REGION_NAME"))
    table_name: str = pdt.Field(default_factory=lambda: f"{os.getenv('ENV')}_positions")

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
                TableName=self.table.name,
                KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "N"}],
                ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
            )
            self._table.meta.client.get_waiter("table_exists").wait(
                TableName=self.table.name
            )
            print(f"Table {self.table.name} created successfully")
        except Exception as e:
            print(f"Error creating table: {e}")

    def insert_position(self, position: Position):
        logger.info("Saving order to the database...")
        try:
            item = position.model_dump()
            item = {k: v for k, v in item.items() if v is not None}
            print("Inserting item:", item)
            self._table.put_item(Item=item)
            logger.info("Position saved successfully")
        except Exception as e:
            logger.error(f"Position saving failed: {e}")
            raise

    def fetch_all_positions(self) -> Positions:
        try:
            response = self._table.scan()
            items = response.get("Items", [])
            orders = [Position(**item) for item in items]
            return Position(orders=orders)
        except Exception as e:
            logger.error(f"Error fetching all positions: {e}")
            return Positions(orders=[])
