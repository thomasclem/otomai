# %% IMPORTS


from pydantic import BaseModel

# %% CANDY BOMBS


class CandyBombActivity(BaseModel):
    activityStatus: int
    airDropTime: str
    airDropTypeList: list[int]
    bizLineLabel: str
    coinContent: list[str]
    coinIcon: str
    contentDTOList: list[str]
    countDownStatus: int
    countDownTime: str
    defaultTemplate: bool
    desc: str
    endTime: str
    iconDtoList: list[str]
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
    rewardCarousels: list[dict]


class GetCurrentCandyBombsResponse(BaseModel):
    notStartedActivities: list = []
    processingActivities: list[CandyBombActivity]
