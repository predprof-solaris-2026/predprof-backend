from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from beanie import Document, Indexed, Link
from pydantic import BaseModel, Field, EmailStr
# from app.data.models import Theme, Difficulty



class Difficulty(str, Enum):
    easy = "лёгкий"
    medium = "средний"
    hard = "сложный"

class Theme(str, Enum):
    math = "математика"
    russian = "русский"
    informatic = "информатика"
    physics = "физика"



# ---------- Common ----------


class TimestampMixin(BaseModel):
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------- PvP (1v1) ----------

class PvpSideState(BaseModel):
    user_id: str
    score: float = 0.0

    # to enforce "replace previous result, do not double points"
    counted_submission_id: Optional[str] = None
    last_submission_id: Optional[str] = None


class PlayerSession(BaseModel):
    """Represents a single player's session in a match."""
    user_id: str
    rating: int
    answer: Optional[str] = None
    submission_count: int = 0
    counted_submission_id: Optional[str] = None
    connected: bool = True


class MatchSessionConfig(BaseModel):
    """Configuration for a PvP match."""
    match_timeout_seconds: int = 600  # 10 minutes
    answer_change_allowed: bool = True  # Allow replacing previous answer


class ThemeStat(BaseModel):
    attempts: int = 0
    correct: int = 0
    avg_time_ms: Optional[float] = None  # optional running average

class UserSchema(BaseModel):
    first_name: str
    last_name: str
    password: str
    email: str
    
class UserLogIn(BaseModel):
    user_token: str
    
class Token(BaseModel):
    access_token: str
    token_type: str

class TaskSchema(BaseModel):
    # subject: Indexed(str)
    id: str
    subject: str
    theme: Theme 
    difficulty: Difficulty 
    title: str
    task_text: str  
    hint: Optional[str] = None
    answer: Optional[str] = None
    is_published: bool = True

class CheckAnswer(BaseModel):
    answer: str