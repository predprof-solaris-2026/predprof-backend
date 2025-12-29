from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from beanie import Document, Indexed, Link
from pydantic import BaseModel, Field, EmailStr
#from app.data.models import Theme, Difficulty



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
    subject: Indexed(str)
    theme: Theme 
    difficulty: Difficulty 
    title: str
    task_text: str  
    hint: str               
    is_published: bool = True

