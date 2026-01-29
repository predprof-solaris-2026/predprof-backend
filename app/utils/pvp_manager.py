"""
Matchmaking and connection management for PvP WebSocket.
"""

import asyncio
import json
from typing import Dict, Optional
from datetime import datetime, timedelta
import uuid

from app.data.models import User, PvpMatch, Task, PvpMatchState, PvpOutcome, UserAggregateStats
from app.data import schemas
from app.utils.elo import update_ratings_after_match
from app.utils.exceptions import Error
from fastapi import WebSocket
from beanie import PydanticObjectId


class PlayerSession:
    def __init__(self, user_id: str, websocket: WebSocket, rating: int):
        self.user_id = user_id
        self.websocket = websocket
        self.rating = rating
        self.answer: Optional[str] = None
        self.submission_count: int = 0
        self.counted_submission_id: Optional[str] = None
        self.connected: bool = True
    

class MatchSession:
    
    MATCH_TIMEOUT_SECONDS = 600 
    ANSWER_CHANGE_ALLOWED = True
    
    def __init__(self, match_id: str, p1_session: PlayerSession, p2_session: Optional[PlayerSession] = None):
        self.match_id = match_id
        self.p1_session = p1_session
        self.p2_session = p2_session
        self.task: Optional[Task] = None
        self.match_model: Optional[PvpMatch] = None
        self.start_time: datetime = datetime.utcnow()

    async def _update_pvp_aggregate(self, user_id: str, result: str):
        # result ∈ {"win","loss","draw"}
        agg = await UserAggregateStats.find_one({"user_id": user_id})
        if not agg:
            agg = UserAggregateStats(user_id=user_id)

        agg.pvp.matches += 1
        if result == "win":
            agg.pvp.wins += 1
        elif result == "loss":
            agg.pvp.losses += 1
        elif result == "draw":
            agg.pvp.draws += 1

        agg.updated_at = datetime.utcnow()
        await agg.save()
    
    async def wait_for_both_players(self, timeout: int = 30) -> bool:
        start = datetime.utcnow()
        while self.p2_session is None:
            if (datetime.utcnow() - start).total_seconds() > timeout:
                await self.p1_session.websocket.send_json({
                    "type": "match_timeout",
                    "message": "Timeout waiting for second player"
                })
                return False
            await asyncio.sleep(0.5)
        
        await self.broadcast({
            "type": "match_start",
            "match_id": self.match_id,
            "players": [self.p1_session.user_id, self.p2_session.user_id]
        })
        return True
    
    async def send_task(self):
        if not self.task:
            return
        
        task_data = {
            "type": "task",
            "task_id": str(self.task.id),
            "title": self.task.title,
            "task_text": self.task.task_text,
            "theme": self.task.theme,
            "difficulty": self.task.difficulty,
            "hint": self.task.hint,
        }
        await self.broadcast(task_data)
    
    def handle_answer_submission(self, player_id: str, answer: str, submission_id: str) -> bool:
        session = self.p1_session if player_id == self.p1_session.user_id else self.p2_session
        
        if session is None or not session.connected:
            return False
        
        if self.ANSWER_CHANGE_ALLOWED:
            if session.counted_submission_id == submission_id:
                session.answer = answer
                return True
            elif session.answer is None:
                session.answer = answer
                session.counted_submission_id = submission_id
                session.submission_count += 1
                return True
            else:
                session.answer = answer
                session.counted_submission_id = submission_id
                return True
        else:
            if session.counted_submission_id is not None:
                return False
            session.answer = answer
            session.counted_submission_id = submission_id
            session.submission_count += 1
            return True
    
    async def broadcast(self, message: dict):
        for session in [self.p1_session, self.p2_session]:
            if session and session.connected:
                try:
                    await session.websocket.send_json(message)
                except Exception:
                    session.connected = False
    
    async def broadcast_state(self):
        state = {
            "type": "state_update",
            "p1": {
                "user_id": self.p1_session.user_id,
                "rating": self.p1_session.rating,
                "answered": self.p1_session.answer is not None,
            },
            "p2": {
                "user_id": self.p2_session.user_id if self.p2_session else None,
                "rating": self.p2_session.rating if self.p2_session else None,
                "answered": (self.p2_session.answer is not None) if self.p2_session else False,
            }
        }
        await self.broadcast(state)

    async def finish_match(self, outcome: str) -> Optional[dict]:
        try:
            # Идемпотентность: выходим, если уже не active
            if self.match_model and self.match_model.state != PvpMatchState.active:
                return None

            allowed = {"p1_win", "p2_win", "draw", "canceled", "technical_error"}
            if outcome not in allowed:
                outcome = "canceled"

            # Сохраняем старые рейтинги ДЛЯ ответа и вычислений
            old_p1 = self.p1_session.rating
            old_p2 = self.p2_session.rating if self.p2_session else None

            new_p1_rating = old_p1
            new_p2_rating = old_p2 if old_p2 is not None else old_p1
            p1_delta = 0
            p2_delta = 0

            # Elo — только для трёх "нормальных" исходов
            if outcome in {"p1_win", "p2_win", "draw"}:
                new_p1_rating, new_p2_rating, p1_delta, p2_delta = update_ratings_after_match(
                    old_p1, new_p2_rating, outcome
                )

            # Обновляем модель матча
            if self.match_model:
                if outcome == "canceled":
                    self.match_model.state = PvpMatchState.canceled
                elif outcome == "technical_error":
                    self.match_model.state = PvpMatchState.technical_error
                else:
                    self.match_model.state = PvpMatchState.finished

                self.match_model.outcome = PvpOutcome(outcome) if outcome in {"p1_win", "p2_win", "draw"} else None
                self.match_model.finished_at = datetime.utcnow()
                self.match_model.p1_rating_delta = p1_delta
                self.match_model.p2_rating_delta = p2_delta if self.p2_session else 0
                await self.match_model.save()

            # Обновляем рейтинги пользователей ТОЛЬКО для win/loss/draw
            if outcome in {"p1_win", "p2_win", "draw"}:
                p1_user = await User.find_one({"_id": PydanticObjectId(self.p1_session.user_id)})
                if p1_user:
                    p1_user.elo_rating = new_p1_rating
                    await p1_user.save()

                if self.p2_session:
                    p2_user = await User.find_one({"_id": PydanticObjectId(self.p2_session.user_id)})
                    if p2_user:
                        p2_user.elo_rating = new_p2_rating
                        await p2_user.save()

                # Обновляем значения в сессии (для последующих сообщений)
                self.p1_session.rating = new_p1_rating
                if self.p2_session:
                    self.p2_session.rating = new_p2_rating

            # Агрегаты — только для win/loss/draw
            if outcome in {"p1_win", "p2_win", "draw"}:
                p1_res = "win" if outcome == "p1_win" else ("loss" if outcome == "p2_win" else "draw")
                p2_res = "win" if outcome == "p2_win" else ("loss" if outcome == "p1_win" else "draw")
                await self._update_pvp_aggregate(self.p1_session.user_id, p1_res)
                if self.p2_session:
                    await self._update_pvp_aggregate(self.p2_session.user_id, p2_res)

            # Формируем ответ, используя старые рейтинги
            result = {
                "type": "match_result",
                "outcome": outcome,
                "p1": {
                    "user_id": self.p1_session.user_id,
                    "old_rating": old_p1,
                    "new_rating": new_p1_rating,
                    "delta": p1_delta,
                },
                "p2": {
                    "user_id": self.p2_session.user_id if self.p2_session else None,
                    "old_rating": old_p2,
                    "new_rating": new_p2_rating if self.p2_session else None,
                    "delta": p2_delta if self.p2_session else 0,
                }
            }
            await self.broadcast(result)
            return result

        except Exception as e:
            print(f"Error finishing match {self.match_id}: {e}")
            return None

class ConnectionManager:    
    def __init__(self):
        self.active_matches: Dict[str, MatchSession] = {}
        self.player_queue: Dict[str, PlayerSession] = {}  # user_id -> PlayerSession
        self.match_lock = asyncio.Lock()
    
    async def queue_player(self, user_id: str, rating: int, websocket: WebSocket) -> Optional[str]:
        async with self.match_lock:
            player = PlayerSession(user_id=user_id, websocket=websocket, rating=rating)
            
            waiting_players = list(self.player_queue.values())
            if waiting_players:
                best_match = None
                for candidate in waiting_players:
                    if abs(candidate.rating - rating) <= 200: 
                        best_match = candidate
                        break
                
                if best_match:
                    del self.player_queue[best_match.user_id]
                    
                    match_id = str(uuid.uuid4())
                    match_session = MatchSession(
                        match_id=match_id,
                        p1_session=best_match,
                        p2_session=player
                    )
                    self.active_matches[match_id] = match_session
                    return match_id
            
            self.player_queue[user_id] = player
            return None
    
    async def remove_player(self, user_id: str):
        async with self.match_lock:
            if user_id in self.player_queue:
                del self.player_queue[user_id]
    
    def get_match(self, match_id: str) -> Optional[MatchSession]:
        return self.active_matches.get(match_id)
    
    async def remove_match(self, match_id: str):
        if match_id in self.active_matches:
            del self.active_matches[match_id]
    
    def get_player_match(self, user_id: str) -> Optional[str]:
        for match_id, match_session in self.active_matches.items():
            if (match_session.p1_session.user_id == user_id or 
                (match_session.p2_session and match_session.p2_session.user_id == user_id)):
                return match_id
        return None


pvp_manager = ConnectionManager()
