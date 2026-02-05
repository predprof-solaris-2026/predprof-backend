from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from beanie import Document, Indexed, Link
from pydantic import BaseModel, Field, EmailStr



class Difficulty(str, Enum):
    easy = "лёгкий"
    medium = "средний"
    hard = "сложный"

class Theme(str, Enum):
    math = "математика"
    russian = "русский"
    informatic = "информатика"
    physics = "физика"



class TimestampMixin(BaseModel):
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PvpSideState(BaseModel):
    user_id: str
    score: float = 0.0

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
    match_timeout_seconds: int = 600 
    answer_change_allowed: bool = True


class ThemeStat(BaseModel):
    attempts: int = 0
    correct: int = 0
    incorrect: int = 0
    avg_time_ms: Optional[float] = None

class UserSchema(BaseModel):
    first_name: str
    last_name: str
    password: str
    email: EmailStr


class AdminSchema(BaseModel):
    first_name: str
    last_name: str
    password: str
    email: EmailStr

class UserResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: str
    elo_rating: int
    is_blocked: bool
    
class UserLogIn(BaseModel):
    user_token: str
    
class Token(BaseModel):
    access_token: str
    token_type: str

class TaskSchema(BaseModel):
    id: str
    subject: str
    theme: Theme 
    difficulty: Difficulty 
    title: str
    task_text: str  
    hint: Optional[str] = None
    answer: Optional[str] = None
    is_published: bool = True

class TaskSchemaRequest(BaseModel):
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
    elapsed_ms: Optional[int] = None

class PersonalRecommendation(BaseModel):
    theme: str
    difficulty: str
    reason: str
    priority: int = Field(description="5 - самый высокий приоритет, 1 - низкий")

class AdaptivePlan(BaseModel):
    user_id: str
    recommendations: List[PersonalRecommendation]
    target_accuracy: float
    target_speed_ms: int
    estimated_completion_days: int


class UserPerformanceMetrics(BaseModel):
    total_attempts: int
    accuracy_rate: float
    avg_response_time_ms: float
    topics_mastered: List[str]
    topics_struggling: List[str]
    topics_not_attempted: List[str]

class HintResponse(BaseModel):
    hint: Optional[str]


class CheckResponse(BaseModel):
    correct: bool


class PlanResponse(BaseModel):
    recommendations: List[PersonalRecommendation]


class TaskRecommendation(BaseModel):
    id: str
    theme: Optional[str] = None
    difficulty: Optional[str] = None
    reason: Optional[str] = None


class DifficultyRecommendation(BaseModel):
    difficulty: str
    recommendation: str


class ThemeResponse(BaseModel):
    theme: str
    recommendations: List[DifficultyRecommendation]
    