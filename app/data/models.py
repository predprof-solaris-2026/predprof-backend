from datetime import datetime

from enum import Enum

from typing import Optional, List, Dict

from beanie import Document, Link, Indexed

from pydantic import BaseModel, Field, EmailStr

from app.data import schemas

from app.data.schemas import Theme, Difficulty

# ---------- Common ----------

class Role(str, Enum):
    user = "user"
    admin = "admin"

    
# ---------- Users / Auth ----------

class User(Document):
    first_name: str
    last_name: str
    email: Indexed(EmailStr, unique=True) 
    password_hash: str                   
    is_blocked: bool = False
    elo_rating: int = 1000

    class Settings:
        name = "users"
        indexes = [
            "is_blocked",
            "elo_rating",
        ]

class Admin(Document):
    first_name: str
    last_name: str
    email: Indexed(EmailStr, unique=True)
    password_hash: str

    class Settings:
        name = "admins"

# ---------- Tasks / Catalog ----------



class Task(Document):
    # subject: Indexed(str)
    subject: str
    theme: str
    difficulty: Difficulty 
    title: str
    task_text: str  
    hint: str               
    answer: Optional[str] = None
    is_published: bool = True

    class Settings:
        name = "tasks"
        indexes = [
            [("subject", 1), ("theme", 1), ("difficulty", 1)],
            "is_published",
            "source",
        ]

# -------------------------------------------


class TrainingSession(Document):
    user_id: Indexed(str) 
    theme: Theme.math
    difficulty: Optional[Difficulty] = None
    elo_rating: int
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None

    class Settings:
        name = "training_sessions"
        indexes = [
            "user_id",
            "started_at",
        ]

# ---------- PvP (1v1) ----------

class PvpMatchState(str, Enum):
    waiting = "waiting"           # created, waiting for 2nd player
    active = "active"             # running
    finished = "finished"         # completed normally
    canceled = "canceled"         # canceled (no rating change)
    technical_error = "technical_error"  # disconnect/tech issue (no rating change)


class PvpOutcome(str, Enum):
    p1_win = "p1_win"
    p2_win = "p2_win"
    draw = "draw"
    canceled = "canceled"
    technical_error = "technical_error"
    
class PvpMatch(Document):
    # matchmaking "by level": store rating at start (snapshot)
    p1_user_id: Indexed(str)
    p2_user_id: Optional[Indexed(str)] = None

    p1_rating_start: int
    p2_rating_start: Optional[int] = None

    task_id: Indexed(str)

    state: PvpMatchState.waiting
    outcome: PvpOutcome = None

    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    p1: schemas.PvpSideState
    p2: Optional[schemas.PvpSideState] = None

    # Elo deltas (persisted so you can audit and avoid recomputation)
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

    avg_time_ms: Optional[float] = None

    #statistics by themes
    by_theme: Dict[str, schemas.ThemeStat] = Field(default_factory=dict)

    class Settings:
        name = "user_stats"
        indexes = ["user_id"]
        
# ---------- Optional: Gamification ----------

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
    """
    SecretAdmin model representing an admin user with additional security attributes.

    Attributes:
        hashed_password (str): Hashed password for the admin user.
    """

    hashed_password: str


class AdminFront(Document):
    """
    AdminFront model representing an admin user for the frontend.

    Attributes:
        username (str): Unique username of the admin.
        disabled (bool): Indicates if the admin account is disabled. Default is False.
        full_name (str): Full name of the admin. Default is None.
        secret (Link[SecretAdmin]): Link to the SecretAdmin document containing security details.
    """

    username: str = Field(unique=True)
    disabled: bool = Field(default=False)
    full_name: str = Field(default=None)
    secret: Link[SecretAdmin] = Field()


class Arrow(Document):
    ids: list[int] = []


class Token(BaseModel):
    """
    Token model representing an access token.

    Attributes:
        access_token (str): The access token string.
        token_type (str): The type of the token, typically "bearer".
    """

    access_token: str
    token_type: str


class TokenData(BaseModel):
    """
    TokenData model representing the data contained in a token.

    Attributes:
        username (str): The username associated with the token.
    """

    username: str
