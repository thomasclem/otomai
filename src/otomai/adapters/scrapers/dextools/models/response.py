from datetime import datetime
from typing import Any

import pandas as pd
from pydantic import BaseModel


class ApiResponse:
    """Simple API response wrapper"""

    def __init__(
        self,
        status_code: int,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        url: str | None = None,
        success: bool = True,
        error_message: str | None = None,
    ):
        self.status_code = status_code
        self.data = data
        self.headers = headers or {}
        self.url = url
        self.success = success
        self.error_message = error_message


class ErrorResponse:
    """Error response model"""

    def __init__(
        self,
        status_code: int,
        error_message: str,
        url: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.status_code = status_code
        self.error_message = error_message
        self.url = url
        self.headers = headers or {}


class Score(BaseModel):
    total: float
    raw: float
    chain: float
    pair: float
    liquidity: float
    dextScore: float
    socialsScore: float | None = None


class PairId(BaseModel):
    chain: str
    exchange: str
    pair: str
    token: str
    tokenRef: str


class DextScore(BaseModel):
    information: int
    holders: int
    pool: int
    transactions: int
    creation: int
    total: int


class Metrics(BaseModel):
    liquidity: float | None = None
    txCount: int
    initialLiquidity: float | None = None
    initialLiquidityUpdatedAt: datetime | None = None
    initialReserve: float | None = None
    initialReserveRef: float | None = None
    liquidityUpdatedAt: datetime | None = None
    reserve: float | None = None
    reserveRef: float | None = None
    balanceLpToken: float | None = None
    balanceLpTokenBurned: float | None = None


class OpenPrice(BaseModel):
    usd: float
    eth: float
    blockNumber: int


class Pool(BaseModel):
    openPrice: OpenPrice | None = None
    tokenAccount0: str | None = None
    tokenAccount1: str | None = None
    sqrtPriceX96: str | None = None
    name: str | None = None
    symbol: str | None = None
    poolId: str | None = None


class Team(BaseModel):
    wallet: str


class PriceInfo(BaseModel):
    usd: dict[str, float]
    chain: dict[str, float]


class LiquidityInfo(BaseModel):
    usd: dict[str, float]


class VolumeInfo(BaseModel):
    total: float
    buys: float
    sells: float


class SwapsInfo(BaseModel):
    total: int
    buys: int
    sells: int


class PeriodStats(BaseModel):
    volume: VolumeInfo
    swaps: SwapsInfo
    price: PriceInfo
    liquidity: LiquidityInfo
    volatility: float | None = None
    makers: int
    updatedAt: datetime


class AllPeriodStats(BaseModel):
    five_m: PeriodStats | None = None
    one_h: PeriodStats | None = None
    six_h: PeriodStats | None = None
    twenty_four_h: PeriodStats | None = None

    class Config:
        allow_population_by_field_name = True
        fields = {"five_m": "5m", "one_h": "1h", "six_h": "6h", "twenty_four_h": "24h"}


class TaxInfo(BaseModel):
    min: float | None = None
    max: float | None = None
    status: str


class ProvidersInfo(BaseModel):
    critical: list[str]
    warning: list[str]
    regular: list[str]


class ReviewInfo(BaseModel):
    critical: list[str]
    warning: list[str]
    regular: list[str]


class SummaryInfo(BaseModel):
    providers: ProvidersInfo
    review: ReviewInfo


class DextoolsAudit(BaseModel):
    is_open_source: str
    is_honeypot: str
    is_mintable: str
    is_proxy: str
    slippage_modifiable: str
    is_blacklisted: str
    sell_tax: TaxInfo
    buy_tax: TaxInfo
    is_contract_renounced: str
    is_potentially_scam: str
    transfer_pausable: str
    summary: SummaryInfo
    updatedAt: datetime


class Audit(BaseModel):
    is_contract_renounced: bool | None = None
    url: str | None = ""
    codeVerified: bool | None = None
    date: datetime | None = None
    lockTransactions: bool | None = None
    mint: bool | None = None
    provider: str | None = None
    proxy: bool | None = None
    status: str | None = None
    unlimitedFees: bool | None = None
    version: int | None = None
    dextools: DextoolsAudit | None = None


class TwitterStatsHistory(BaseModel):
    followers: int
    updatedAt: datetime


class TwitterStats(BaseModel):
    followers: int | str | None = None
    history: list[TwitterStatsHistory] | str | None = None


class TokenInfo(BaseModel):
    blueCheckmark: str | None = None
    cmc: str | None = ""
    coingecko: str | None = ""
    description: str | None = ""
    dextools: bool | None = False
    dextoolsUpdatedAt: datetime | None = None
    email: str | None = ""
    extraInfo: str | None = ""
    nftCollection: str | None = ""
    twitterStats: TwitterStats | None = None
    ventures: bool | None = False


class TokenLinks(BaseModel):
    bitbucket: str | None = ""
    discord: str | None = ""
    facebook: str | None = ""
    github: str | None = ""
    instagram: str | None = ""
    linkedin: str | None = ""
    medium: str | None = ""
    reddit: str | None = ""
    slack: str | None = ""
    telegram: str | None = ""
    tiktok: str | None = ""
    twitter: str | None = ""
    twitterPost: str | None = ""
    website: str | None = ""
    youtube: str | None = ""


class TokenMetrics(BaseModel):
    circulatingSupply: float | None = None
    maxSupply: float | None = None
    totalSupply: float | None = None
    totalSupplyUpdatedAt: datetime | None = None
    holdersUpdatedAt: datetime | None = None
    holders: int | None = None
    fdv: float | None = None
    txCount: int | None = None


class ReprPair(BaseModel):
    id: PairId
    updatedAt: datetime


class Deployment(BaseModel):
    createdAt: datetime
    createdAtBlockNumber: int
    factory: str
    owner: str
    updatedAt: datetime


class Disclaimer(BaseModel):
    type: str
    level: str | None = None
    title: str
    date: datetime
    lastUpdate: datetime


class Token(BaseModel):
    audit: Audit | None = None
    decimals: int | None = None
    locks: list[Any] | None = []
    name: str | None = ""
    symbol: str | None = ""
    totalSupply: str | None = ""
    banner: str | None = ""
    categories: list[str | int] | None = []
    info: TokenInfo | None = None
    links: TokenLinks | None = None
    logo: str | None = ""
    logoOnchain: str | None = ""
    metrics: TokenMetrics | None = None
    creationBlock: int | None = None
    creationTime: datetime | None = None
    reprPair: ReprPair | None = None
    rugPulledAt: list[str] | None = None
    deployment: Deployment | None = None
    disclaimers: dict[str, Disclaimer] | None = None


class Votes(BaseModel):
    warning: int | None = 0
    downvotes: int | None = 0
    upvotes: int | None = 0

    class Config:
        allow_population_by_field_name = True
        fields = {"warning": "_warning"}


class Nitro(BaseModel):
    total: int | None
    lastNitro: datetime | None
    tickers: list[dict[str, int]] | None


class RugPull(BaseModel):
    priceDrop: bool | None = None
    liquidityRemoved: bool | None = None


class FirstMakers(BaseModel):
    snipers: list[str] | None = None
    others: list[str] | None = None


class PairResult(BaseModel):
    score: Score
    id: PairId
    creationBlock: int | None = None
    creationTime: datetime | None = None
    creationTransaction: str | None = None
    dextScore: DextScore
    fee: float | None = None
    metrics: Metrics
    name: str
    nameRef: str
    symbol: str
    symbolRef: str
    type: str
    locks: list[Any] | None = []
    pool: Pool | None = None
    team: Team | None = None
    firstSwapTimestamp: datetime | None = None
    periodStats: AllPeriodStats | None = None
    alias: str | None = None
    votes: Votes | None = None
    price: float | None = None
    priceTime: datetime | None = None
    token: Token
    price24h: float | None = None
    volume: float | None = None
    swaps: int | None = None
    nitro: Nitro | None = None
    rugPull: RugPull | None = None
    firstMakers: FirstMakers | None = None
    openTime: datetime | None = None


class ChainCount(BaseModel):
    id: str | None = None
    count: int | None = 0

    class Config:
        allow_population_by_field_name = True
        fields = {"id": "_id"}


class InfoSection(BaseModel):
    chains: list[ChainCount]
    chainsTotal: list[ChainCount]
    count: int
    countTotal: int


class PairSearchResponse(BaseModel):
    """
    Response model for DexTools pair search API.

    Contains search results with trading pairs, token information,
    market data, and metadata about the search.
    """

    results: list[PairResult]
    info: InfoSection | None = None
    sponsored: list[Any] | None = []

    class Config:
        # Allow extra fields in case API adds new ones
        extra = "allow"
        # Use enum values for serialization
        use_enum_values = True
        # Allow population by field name for aliases
        allow_population_by_field_name = True

    def to_dataframe(self, flatten: bool = True):
        """
        Convert search results to a pandas DataFrame.

        Args:
            flatten: If True, normalizes nested JSON structure into flat columns

        Returns:
            pandas.DataFrame: DataFrame containing all pair results

        Raises:
            ImportError: If pandas is not installed
        """
        if not self.results:
            # Return empty DataFrame with expected columns if no results
            return pd.DataFrame()

        if flatten:
            # Flatten nested structure using json_normalize
            return pd.concat(
                [pd.json_normalize(result.dict()) for result in self.results],
                ignore_index=True,
            )
        else:
            # Simple DataFrame with dict conversion
            return pd.DataFrame([result.model_dump() for result in self.results])
