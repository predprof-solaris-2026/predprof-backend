from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, EmailStr, Field

from app.data.models import User, UserAggregateStats
from app.utils.exceptions import Error
from app.utils.security import get_current_user, get_current_admin

router = APIRouter(prefix="/stats", tags=["Stats"])


class StatsPvp(BaseModel):
    matches: int
    wins: int
    losses: int
    draws: int
    win_rate_pct: float


class StatsTrainingByThemeItem(BaseModel):
    attempts: int
    correct: int
    incorrect: int
    accuracy_pct: float
    avg_time_ms: Optional[float] = None


class StatsTraining(BaseModel):
    attempts: int
    correct: int
    incorrect: int
    accuracy_pct: float
    avg_time_ms: Optional[float] = None
    by_theme: Dict[str, StatsTrainingByThemeItem]


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    first_name: str
    last_name: str
    elo_rating: int
    is_blocked: bool


class StatsResponse(BaseModel):
    user: UserPublic
    pvp: StatsPvp
    training: StatsTraining
    updated_at: datetime = Field(default_factory=datetime.utcnow)


async def _get_user_or_404(user_id: str) -> User:
    user = await User.find_one(User.id == PydanticObjectId(user_id))
    if not user:
        raise Error.USER_NOT_FOUND
    return user


def _build_pvp_summary(agg: UserAggregateStats) -> StatsPvp:
    m = agg.pvp.matches or 0
    w = agg.pvp.wins or 0
    l = agg.pvp.losses or 0
    d = agg.pvp.draws or 0
    win_rate = (w / m * 100.0) if m > 0 else 0.0
    return StatsPvp(matches=m, wins=w, losses=l, draws=d, win_rate_pct=round(win_rate, 2))


def _build_training_summary(agg: UserAggregateStats) -> StatsTraining:
    attempts = agg.training.attempts or 0
    correct = agg.training.correct or 0
    incorrect = agg.training.incorrect or max(0, attempts - correct)
    accuracy = (correct / attempts * 100.0) if attempts > 0 else 0.0

    by_theme_resp: Dict[str, StatsTrainingByThemeItem] = {}
    sum_time = 0.0
    sum_attempts_time = 0

    for theme_key, tstat in (agg.training.by_theme or {}).items():
        t_attempts = tstat.attempts or 0
        t_correct = tstat.correct or 0
        t_incorrect = max(0, t_attempts - t_correct)
        t_accuracy = (t_correct / t_attempts * 100.0) if t_attempts > 0 else 0.0

        by_theme_resp[theme_key] = StatsTrainingByThemeItem(
            attempts=t_attempts,
            correct=t_correct,
            incorrect=t_incorrect,
            accuracy_pct=round(t_accuracy, 2),
            avg_time_ms=tstat.avg_time_ms
        )

        if tstat.avg_time_ms is not None and t_attempts > 0:
            sum_time += float(tstat.avg_time_ms) * t_attempts
            sum_attempts_time += t_attempts

    weighted_avg_time = (sum_time / sum_attempts_time) if sum_attempts_time > 0 else None

    return StatsTraining(
        attempts=attempts,
        correct=correct,
        incorrect=incorrect,
        accuracy_pct=round(accuracy, 2),
        avg_time_ms=weighted_avg_time,
        by_theme=by_theme_resp
    )


async def _load_agg_or_default(user_id: str) -> UserAggregateStats:
    agg = await UserAggregateStats.find_one({"user_id": user_id})
    if not agg:
        agg = UserAggregateStats(user_id=user_id) 
    return agg


def _user_public(u: User) -> UserPublic:
    return UserPublic(
        id=str(u.id),
        email=u.email,
        first_name=u.first_name,
        last_name=u.last_name,
        elo_rating=u.elo_rating,
        is_blocked=u.is_blocked
    )


@router.get("/me", response_model=StatsResponse)
async def get_my_stats(current_user: User = Depends(get_current_user)) -> StatsResponse:
    user = current_user 
    agg = await _load_agg_or_default(str(user.id))

    return StatsResponse(
        user=_user_public(user),
        pvp=_build_pvp_summary(agg),
        training=_build_training_summary(agg),
        updated_at=agg.updated_at,
    )


@router.get("/users/{user_id}", response_model=StatsResponse)
async def get_user_stats(
    user_id: str = Path(..., description="ID пользователя"),
    _admin=Depends(get_current_admin)
) -> StatsResponse:
    user = await _get_user_or_404(user_id)
    agg = await _load_agg_or_default(user_id)

    return StatsResponse(
        user=_user_public(user),
        pvp=_build_pvp_summary(agg),
        training=_build_training_summary(agg),
        updated_at=agg.updated_at,
    )