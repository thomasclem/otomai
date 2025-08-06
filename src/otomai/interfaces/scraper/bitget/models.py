# %% IMPORTS

from typing import List, Dict
from pydantic import BaseModel

# %% CANDY BOMBS


class CandyBombActivity(BaseModel):
    activityStatus: int
    airDropTime: str
    airDropTypeList: List[int]
    bizLineLabel: str
    coinContent: List[str]
    coinIcon: str
    contentDTOList: List[str]
    countDownStatus: int
    countDownTime: str
    defaultTemplate: bool
    desc: str
    endTime: str
    iconDtoList: List[str]
    id: str
    ieoTotal: int
    ieoTotalUsdt: float
    imgUrl: str
    infiniteMode: int
    inviteStatus: int
    isTop: int
    localInviteStatus: bool
    name: str
    newContractUserLabel: bool
    newContractUserSignUp: bool
    newConvertUserLabel: bool
    newConvertUserSignUp: bool
    newUserLabel: bool
    newUserSignUp: bool
    newUserStatus: bool
    oldUserLabel: bool
    oldUserSignUp: bool
    oldUserStatus: bool
    remind: bool
    rewardCarousels: List[Dict]


class GetCurrentCandyBombsResponse(BaseModel):
    notStartedActivities: List = []
    processingActivities: List[CandyBombActivity]
