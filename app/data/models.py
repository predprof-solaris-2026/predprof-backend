from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict

from beanie import Document, Indexed, Link
from pydantic import BaseModel, Field, EmailStr
from app.data import schemas
from app.data.schemas import Theme, Difficulty


class PvpCounters(BaseModel):
    matches: int = 0 
    wins: int = 0
    losses: int = 0
    draws: int = 0


class TrainingCounters(BaseModel):
    attempts: int = 0
    correct: int = 0
    incorrect: int = 0
    by_theme: Dict[str, schemas.ThemeStat] = Field(default_factory=dict)


class UserAggregateStats(Document):
    user_id: Indexed(str, unique=True)
    pvp: PvpCounters = Field(default_factory=PvpCounters)
    training: TrainingCounters = Field(default_factory=TrainingCounters)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "user_aggregate_stats"
        indexes = ["user_id"]


class User(Document):
    first_name: str
    last_name: str
    email: Indexed(EmailStr, unique=True)
    password_hash: str
    is_blocked: bool = False
    elo_rating: int = 1000

    class Settings:
        name = "users"
        indexes = ["is_blocked", "elo_rating"]


class Admin(Document):
    first_name: str
    last_name: str
    email: Indexed(EmailStr, unique=True)
    password_hash: str

    class Settings:
        name = "admins"


class Task(Document):
    subject: str
    theme: Theme
    difficulty: Difficulty
    title: str
    task_text: str
    hint: Optional[str] = None
    answer: Optional[str] = None
    is_published: bool = True

    class Settings:
        name = "tasks"
        indexes = [
            [("subject", 1), ("theme", 1), ("difficulty", 1)],
            "is_published", "source"
        ]


class TrainingSession(Document):
    user_id: Indexed(str)
    theme: Theme
    difficulty: Optional[Difficulty] = None
    elo_rating: int
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None

    class Settings:
        name = "training_sessions"
        indexes = ["user_id", "started_at"]


class PvpMatchState(str, Enum):
    waiting = "waiting"
    active = "active"
    finished = "finished"
    canceled = "canceled"
    technical_error = "technical_error"


class PvpOutcome(str, Enum):
    p1_win = "p1_win"
    p2_win = "p2_win"
    draw = "draw"
    canceled = "canceled"
    technical_error = "technical_error"


class PvpMatch(Document):
    p1_user_id: Indexed(str)
    p2_user_id: Optional[Indexed(str)] = None
    p1_rating_start: int
    p2_rating_start: Optional[int] = None
    task_id: Indexed(str)
    state: PvpMatchState = PvpMatchState.waiting
    outcome: Optional[PvpOutcome] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    p1: schemas.PvpSideState
    p2: Optional[schemas.PvpSideState] = None
    p1_rating_delta: int = 0
    p2_rating_delta: int = 0

    class Settings:
        name = "pvp_matches"
        indexes = [
            "state",
            "task_id",
            "started_at",
            [("p1_user_id", 1), ("created_at", -1)],
            [("p2_user_id", 1), ("created_at", -1)],
        ]


class UserStats(Document):
    user_id: Indexed(str, unique=True)
    attempts: int = 0
    correct: int = 0
    incorrect: int = 0
    avg_time_ms: Optional[float] = None
    hints_used: int = 0
    pvp_matches: int = 0
    pvp_wins: int = 0
    pvp_losses: int = 0
    pvp_draws: int = 0
    by_theme: Dict[str, schemas.ThemeStat] = Field(default_factory=dict)

    class Settings:
        name = "user_stats"
        indexes = ["user_id"]


class AchievementDefinition(Document):
    code: Indexed(str, unique=True)
    title: str
    description: Optional[str] = None
    points: int = 0

    class Settings:
        name = "achievement_definitions"


class UserAchievement(Document):
    user_id: Indexed(str)
    achievement_code: Indexed(str)
    unlocked_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "user_achievements"
        indexes = [
            [("user_id", 1), ("achievement_code", 1)],
        ]


class SecretAdmin(Document):
    hashed_password: str

    class Settings:
        name = "secret_admins"


class AdminFront(Document):
    username: str = Field(unique=True)
    disabled: bool = Field(default=False)
    full_name: Optional[str] = Field(default=None)
    secret: Link[SecretAdmin]

    class Settings:
        name = "admin_front"


class Arrow(Document):
    ids: list[int] = Field(default_factory=list)

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str