from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel
from datetime import datetime
import pandas as pd


class ApiResponse:
    """Simple API response wrapper"""

    def __init__(
        self,
        status_code: int,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        url: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
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
        url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
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
    socialsScore: Optional[float] = None


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
    liquidity: Optional[float] = None
    txCount: int
    initialLiquidity: Optional[float] = None
    initialLiquidityUpdatedAt: Optional[datetime] = None
    initialReserve: Optional[float] = None
    initialReserveRef: Optional[float] = None
    liquidityUpdatedAt: Optional[datetime] = None
    reserve: Optional[float] = None
    reserveRef: Optional[float] = None
    balanceLpToken: Optional[float] = None
    balanceLpTokenBurned: Optional[float] = None


class OpenPrice(BaseModel):
    usd: float
    eth: float
    blockNumber: int


class Pool(BaseModel):
    openPrice: Optional[OpenPrice] = None
    tokenAccount0: Optional[str] = None
    tokenAccount1: Optional[str] = None
    sqrtPriceX96: Optional[str] = None
    name: Optional[str] = None
    symbol: Optional[str] = None
    poolId: Optional[str] = None


class Team(BaseModel):
    wallet: str


class PriceInfo(BaseModel):
    usd: Dict[str, float]
    chain: Dict[str, float]


class LiquidityInfo(BaseModel):
    usd: Dict[str, float]


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
    volatility: Optional[float] = None
    makers: int
    updatedAt: datetime


class AllPeriodStats(BaseModel):
    five_m: Optional[PeriodStats] = None
    one_h: Optional[PeriodStats] = None
    six_h: Optional[PeriodStats] = None
    twenty_four_h: Optional[PeriodStats] = None

    class Config:
        allow_population_by_field_name = True
        fields = {"five_m": "5m", "one_h": "1h", "six_h": "6h", "twenty_four_h": "24h"}


class TaxInfo(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    status: str


class ProvidersInfo(BaseModel):
    critical: List[str]
    warning: List[str]
    regular: List[str]


class ReviewInfo(BaseModel):
    critical: List[str]
    warning: List[str]
    regular: List[str]


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
    is_contract_renounced: Optional[bool] = None
    url: Optional[str] = ""
    codeVerified: Optional[bool] = None
    date: Optional[datetime] = None
    lockTransactions: Optional[bool] = None
    mint: Optional[bool] = None
    provider: Optional[str] = None
    proxy: Optional[bool] = None
    status: Optional[str] = None
    unlimitedFees: Optional[bool] = None
    version: Optional[int] = None
    dextools: Optional[DextoolsAudit] = None


class TwitterStatsHistory(BaseModel):
    followers: int
    updatedAt: datetime


class TwitterStats(BaseModel):
    followers: Union[int, str, None] = None
    history: Union[List[TwitterStatsHistory], str, None] = None


class TokenInfo(BaseModel):
    blueCheckmark: Optional[str] = None
    cmc: Optional[str] = ""
    coingecko: Optional[str] = ""
    description: Optional[str] = ""
    dextools: Optional[bool] = False
    dextoolsUpdatedAt: Optional[datetime] = None
    email: Optional[str] = ""
    extraInfo: Optional[str] = ""
    nftCollection: Optional[str] = ""
    twitterStats: Optional[TwitterStats] = None
    ventures: Optional[bool] = False


class TokenLinks(BaseModel):
    bitbucket: Optional[str] = ""
    discord: Optional[str] = ""
    facebook: Optional[str] = ""
    github: Optional[str] = ""
    instagram: Optional[str] = ""
    linkedin: Optional[str] = ""
    medium: Optional[str] = ""
    reddit: Optional[str] = ""
    slack: Optional[str] = ""
    telegram: Optional[str] = ""
    tiktok: Optional[str] = ""
    twitter: Optional[str] = ""
    twitterPost: Optional[str] = ""
    website: Optional[str] = ""
    youtube: Optional[str] = ""


class TokenMetrics(BaseModel):
    circulatingSupply: Optional[float] = None
    maxSupply: Optional[float] = None
    totalSupply: Optional[float] = None
    totalSupplyUpdatedAt: Optional[datetime] = None
    holdersUpdatedAt: Optional[datetime] = None
    holders: Optional[int] = None
    fdv: Optional[float] = None
    txCount: Optional[int] = None


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
    level: Optional[str] = None
    title: str
    date: datetime
    lastUpdate: datetime


class Token(BaseModel):
    audit: Optional[Audit] = None
    decimals: Optional[int] = None
    locks: Optional[List[Any]] = []
    name: Optional[str] = ""
    symbol: Optional[str] = ""
    totalSupply: Optional[str] = ""
    banner: Optional[str] = ""
    categories: Optional[List[Union[str, int]]] = []
    info: Optional[TokenInfo] = None
    links: Optional[TokenLinks] = None
    logo: Optional[str] = ""
    logoOnchain: Optional[str] = ""
    metrics: Optional[TokenMetrics] = None
    creationBlock: Optional[int] = None
    creationTime: Optional[datetime] = None
    reprPair: Optional[ReprPair] = None
    rugPulledAt: Optional[List[str]] = None
    deployment: Optional[Deployment] = None
    disclaimers: Optional[Dict[str, Disclaimer]] = None


class Votes(BaseModel):
    warning: Optional[int] = 0
    downvotes: Optional[int] = 0
    upvotes: Optional[int] = 0

    class Config:
        allow_population_by_field_name = True
        fields = {"warning": "_warning"}


class Nitro(BaseModel):
    total: Optional[int]
    lastNitro: Optional[datetime]
    tickers: Optional[List[Dict[str, int]]]


class RugPull(BaseModel):
    priceDrop: Optional[bool] = None
    liquidityRemoved: Optional[bool] = None


class FirstMakers(BaseModel):
    snipers: Optional[List[str]] = None
    others: Optional[List[str]] = None


class PairResult(BaseModel):
    score: Score
    id: PairId
    creationBlock: Optional[int] = None
    creationTime: Optional[datetime] = None
    creationTransaction: Optional[str] = None
    dextScore: DextScore
    fee: Optional[float] = None
    metrics: Metrics
    name: str
    nameRef: str
    symbol: str
    symbolRef: str
    type: str
    locks: Optional[List[Any]] = []
    pool: Optional[Pool] = None
    team: Optional[Team] = None
    firstSwapTimestamp: Optional[datetime] = None
    periodStats: Optional[AllPeriodStats] = None
    alias: Optional[str] = None
    votes: Optional[Votes] = None
    price: Optional[float] = None
    priceTime: Optional[datetime] = None
    token: Token
    price24h: Optional[float] = None
    volume: Optional[float] = None
    swaps: Optional[int] = None
    nitro: Optional[Nitro] = None
    rugPull: Optional[RugPull] = None
    firstMakers: Optional[FirstMakers] = None
    openTime: Optional[datetime] = None


class ChainCount(BaseModel):
    id: Optional[str] = None
    count: Optional[int] = 0

    class Config:
        allow_population_by_field_name = True
        fields = {"id": "_id"}


class InfoSection(BaseModel):
    chains: List[ChainCount]
    chainsTotal: List[ChainCount]
    count: int
    countTotal: int


class PairSearchResponse(BaseModel):
    """
    Response model for DexTools pair search API.

    Contains search results with trading pairs, token information,
    market data, and metadata about the search.
    """

    results: List[PairResult]
    info: Optional[InfoSection] = None
    sponsored: Optional[List[Any]] = []

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
