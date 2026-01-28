from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, EmailStr, Field

from app.data.models import User, PvpMatch, UserAggregateStats, PvpMatchState
from app.utils.security import get_current_user, get_current_admin
from app.utils.elo import calculate_win_probability, calculate_elo_change

router = APIRouter(prefix="/rating", tags=["Rating"])


# ---------- Response Schemas ----------
class UserPublic(BaseModel):
    id: str
    email: EmailStr
    first_name: str
    last_name: str
    elo_rating: int
    is_blocked: bool


class PvpSummary(BaseModel):
    matches: int
    wins: int
    losses: int
    draws: int
    win_rate_pct: float


class RatingSummary(BaseModel):
    user: UserPublic
    rank: int
    percentile_pct: float
    total_players: int
    pvp: PvpSummary
    updated_at: Optional[datetime] = None


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    email: EmailStr
    name: str
    rating: int


class LeaderboardResponse(BaseModel):
    total: int
    offset: int
    limit: int
    entries: List[LeaderboardEntry]


class ProbabilityResponse(BaseModel):
    my_rating: int
    opponent_rating: int
    expected_score: float  # вероятность победы по формуле Elo (ожидаемый счёт), 0..1


class ProjectionDeltas(BaseModel):
    win: int
    draw: int
    loss: int


class ProjectionResponse(BaseModel):
    my_rating: int
    opponent_rating: int
    k_factor: int = 32
    deltas: ProjectionDeltas


class MatchHistoryItem(BaseModel):
    match_id: str
    opponent_id: Optional[str]
    my_rating_before: int
    my_rating_delta: int
    outcome: Optional[str] = None
    state: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class MatchHistoryResponse(BaseModel):
    items: List[MatchHistoryItem]
    limit: int


# ---------- Helpers ----------
def _user_public(u: User) -> UserPublic:
    return UserPublic(
        id=str(u.id),
        email=u.email,
        first_name=u.first_name,
        last_name=u.last_name,
        elo_rating=u.elo_rating,
        is_blocked=u.is_blocked,
    )


async def _get_user_by_id_or_404(user_id: str) -> User:
    try:
        oid = PydanticObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=404, detail="User not found")
    user = await User.find_one(User.id == oid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def _get_pvp_summary(user_id: str) -> PvpSummary:
    agg = await UserAggregateStats.find_one({"user_id": user_id})
    if not agg:
        return PvpSummary(matches=0, wins=0, losses=0, draws=0, win_rate_pct=0.0)
    m = agg.pvp.matches or 0
    w = agg.pvp.wins or 0
    l = agg.pvp.losses or 0
    d = agg.pvp.draws or 0
    win_rate = (w / m * 100.0) if m > 0 else 0.0
    return PvpSummary(matches=m, wins=w, losses=l, draws=d, win_rate_pct=round(win_rate, 2))


async def _rank_and_percentile(my_rating: int) -> tuple[int, float, int]:
    # ранг — количество пользователей с рейтингом строго выше + 1 (tie получают одинаковый ранг)
    total = await User.find({"is_blocked": False}).count()
    if total == 0:
        return 1, 0.0, 0
    higher = await User.find({"is_blocked": False, "elo_rating": {"$gt": my_rating}}).count()
    lower = await User.find({"is_blocked": False, "elo_rating": {"$lt": my_rating}}).count()
    rank = higher + 1
    percentile = (lower / total) * 100.0
    return rank, round(percentile, 2), total


# ---------- Endpoints ----------
@router.get("/me", response_model=RatingSummary)
async def get_my_rating(current_user: User = Depends(get_current_user)) -> RatingSummary:
    rank, percentile, total = await _rank_and_percentile(current_user.elo_rating)
    pvp = await _get_pvp_summary(str(current_user.id))
    # пробуем взять timestamp обновления из агрегатов
    agg = await UserAggregateStats.find_one({"user_id": str(current_user.id)})
    return RatingSummary(
        user=_user_public(current_user),
        rank=rank,
        percentile_pct=percentile,
        total_players=total,
        pvp=pvp,
        updated_at=agg.updated_at if agg else None,
    )


@router.get("/users/{user_id}", response_model=RatingSummary)
async def get_user_rating(
    user_id: str = Path(..., description="ID пользователя"),
    _admin=Depends(get_current_admin),
) -> RatingSummary:
    user = await _get_user_by_id_or_404(user_id)
    rank, percentile, total = await _rank_and_percentile(user.elo_rating)
    pvp = await _get_pvp_summary(user_id)
    agg = await UserAggregateStats.find_one({"user_id": user_id})
    return RatingSummary(
        user=_user_public(user),
        rank=rank,
        percentile_pct=percentile,
        total_players=total,
        pvp=pvp,
        updated_at=agg.updated_at if agg else None,
    )


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> LeaderboardResponse:
    total = await User.find({"is_blocked": False}).count()
    players = (
        await User.find({"is_blocked": False})
        .sort([("elo_rating", -1), ("_id", 1)])
        .skip(offset)
        .limit(limit)
        .to_list()
    )
    entries = [
        LeaderboardEntry(
            rank=offset + i + 1,
            user_id=str(u.id),
            email=u.email,
            name=f"{u.first_name} {u.last_name}".strip(),
            rating=u.elo_rating,
        )
        for i, u in enumerate(players)
    ]
    return LeaderboardResponse(total=total, offset=offset, limit=limit, entries=entries)


@router.get("/probability", response_model=ProbabilityResponse)
async def get_win_probability(
    opponent_id: Optional[str] = Query(None, description="ID соперника"),
    opponent_rating: Optional[int] = Query(None, ge=0, description="Рейтинг соперника"),
    current_user: User = Depends(get_current_user),
) -> ProbabilityResponse:
    if not opponent_id and opponent_rating is None:
        raise HTTPException(status_code=400, detail="Provide opponent_id or opponent_rating")

    opp_rating: int
    if opponent_id:
        opp_user = await _get_user_by_id_or_404(opponent_id)
        opp_rating = opp_user.elo_rating
    else:
        opp_rating = int(opponent_rating or 0)

    expected = calculate_win_probability(current_user.elo_rating, opp_rating)
    return ProbabilityResponse(
        my_rating=current_user.elo_rating,
        opponent_rating=opp_rating,
        expected_score=round(float(expected), 4),
    )


@router.get("/projection", response_model=ProjectionResponse)
async def get_rating_projection(
    opponent_id: Optional[str] = Query(None, description="ID соперника"),
    opponent_rating: Optional[int] = Query(None, ge=0, description="Рейтинг соперника"),
    k_factor: int = Query(32, ge=1, le=128),
    current_user: User = Depends(get_current_user),
) -> ProjectionResponse:
    if not opponent_id and opponent_rating is None:
        raise HTTPException(status_code=400, detail="Provide opponent_id or opponent_rating")

    opp_rating: int
    if opponent_id:
        opp_user = await _get_user_by_id_or_404(opponent_id)
        opp_rating = opp_user.elo_rating
    else:
        opp_rating = int(opponent_rating or 0)

    win_delta = calculate_elo_change(current_user.elo_rating, opp_rating, 1.0, k_factor)
    draw_delta = calculate_elo_change(current_user.elo_rating, opp_rating, 0.5, k_factor)
    loss_delta = calculate_elo_change(current_user.elo_rating, opp_rating, 0.0, k_factor)

    return ProjectionResponse(
        my_rating=current_user.elo_rating,
        opponent_rating=opp_rating,
        k_factor=k_factor,
        deltas=ProjectionDeltas(win=win_delta, draw=draw_delta, loss=loss_delta),
    )


@router.get("/history/me", response_model=MatchHistoryResponse)
async def get_my_rating_history(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
) -> MatchHistoryResponse:
    user_id = str(current_user.id)
    # последние матчи пользователя (оба направления) — сортируем по finished_at убыв.
    matches = (
        await PvpMatch.find(
            {"$or": [{"p1_user_id": user_id}, {"p2_user_id": user_id}]}
        )
        .sort([("finished_at", -1), ("started_at", -1)])
        .limit(limit)
        .to_list()
    )
    items: List[MatchHistoryItem] = []
    for m in matches:
        is_p1 = (m.p1_user_id == user_id)
        opponent_id = m.p2_user_id if is_p1 else m.p1_user_id
        my_before = m.p1_rating_start if is_p1 else (m.p2_rating_start or m.p1_rating_start)
        my_delta = m.p1_rating_delta if is_p1 else m.p2_rating_delta
        items.append(
            MatchHistoryItem(
                match_id=str(m.id),
                opponent_id=opponent_id,
                my_rating_before=my_before,
                my_rating_delta=my_delta,
                outcome=m.outcome.value if getattr(m, "outcome", None) else None,
                state=m.state.value if isinstance(m.state, PvpMatchState) else str(m.state),
                started_at=m.started_at,
                finished_at=m.finished_at,
            )
        )
    return MatchHistoryResponse(items=items, limit=limit)