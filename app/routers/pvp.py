
import asyncio
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from app.data.models import User, PvpMatch, Task, PvpMatchState
from app.utils.security import get_current_user
from app.utils.pvp_manager import pvp_manager, MatchSession
from app.data import schemas
from datetime import datetime

router = APIRouter(prefix="/pvp", tags=["PvP"])


@router.websocket("/")
async def websocket_pvp_match(websocket: WebSocket):
    """
    1. Client connects with JWT token
    2. Player added to matchmaking queue
    3. When paired: both players receive task
    4. Players submit answers with submission IDs
    5. Match result calculated (win/loss/draw)
    6. Elo ratings updated and persisted
    7. Result sent to both players
    """
    await websocket.accept()
    
    try:
        token = None
        msg = await websocket.receive_json()
        if msg.get("type") == "auth":
            token = msg.get("token")
        
        if not token:
            await websocket.send_json({"type": "error", "message": "Missing authentication token"})
            await websocket.close(code=1008)
            return
        
        user = await get_current_user_websocket(token)
        user_id = str(user.id)
        
        match_id = await pvp_manager.queue_player(user_id, user.elo_rating, websocket)
        
        if match_id:
            match_session = pvp_manager.get_match(match_id)
            await handle_active_match(match_session, user_id)
        else:
            await handle_queued_player(user_id, websocket, user.elo_rating)
    
    except WebSocketDisconnect:
        await pvp_manager.remove_player(user_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await websocket.close(code=1011)
        except:
            pass


async def handle_queued_player(user_id: str, websocket: WebSocket, rating: int):
    try:
        await websocket.send_json({
            "type": "queued",
            "message": "Waiting for opponent...",
            "rating": rating
        })
        
        while True:
            msg = await websocket.receive_json()
            
            if msg.get("type") == "cancel":
                await pvp_manager.remove_player(user_id)
                await websocket.send_json({"type": "canceled", "message": "Removed from queue"})
                break
            
            match_id = pvp_manager.get_player_match(user_id)
            if match_id:
                match_session = pvp_manager.get_match(match_id)
                await handle_active_match(match_session, user_id)
                break
    
    except WebSocketDisconnect:
        await pvp_manager.remove_player(user_id)


async def handle_active_match(match_session: MatchSession, current_user_id: str):    
    if not match_session.p2_session:
        if not await match_session.wait_for_both_players(timeout=30):
            return
        
    if (current_user_id != match_session.p1_session.user_id and 
        current_user_id != match_session.p2_session.user_id):
        await match_session.p1_session.websocket.send_json({
            "type": "error",
            "message": "User not part of this match"
        })
        return
    
    try:
        task = await Task.find_one(Task.is_published == True)
        if not task:
            await match_session.broadcast({"type": "error", "message": "No tasks available"})
            return
        
        match_session.task = task
        
        match_session.match_model = PvpMatch(
            p1_user_id=match_session.p1_session.user_id,
            p2_user_id=match_session.p2_session.user_id,
            p1_rating_start=match_session.p1_session.rating,
            p2_rating_start=match_session.p2_session.rating,
            task_id=str(task.id),
            state=PvpMatchState.active,
            started_at=datetime.utcnow(),
            p1=schemas.PvpSideState(user_id=match_session.p1_session.user_id),
            p2=schemas.PvpSideState(user_id=match_session.p2_session.user_id),
        )
        await match_session.match_model.save()
        
        await match_session.send_task()
        
        answer_timeout = 300
        start_time = datetime.utcnow()
        
        while (datetime.utcnow() - start_time).total_seconds() < answer_timeout:
            if match_session.p1_session.answer and match_session.p2_session.answer:
                break
            
            try:
                websocket = match_session.p1_session.websocket if current_user_id == match_session.p1_session.user_id else match_session.p2_session.websocket
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=1.0)
                
                if msg.get("type") == "answer":
                    submission_id = msg.get("submission_id", str(uuid.uuid4()))
                    answer = msg.get("answer", "")
                    
                    counted = match_session.handle_answer_submission(current_user_id, answer, submission_id)
                    
                    await websocket.send_json({
                        "type": "answer_received",
                        "submission_id": submission_id,
                        "counted": counted,
                        "message": "Answer recorded" if counted else "Answer rejected (duplicate)"
                    })
                    
                    await match_session.broadcast_state()
                
                elif msg.get("type") == "disconnect":
                    await match_session.finish_match("technical_error")
                    return
            
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"Error receiving answer: {e}")
                break
        
        if match_session.p1_session.answer and match_session.p2_session.answer:
            if match_session.p1_session.answer == match_session.p2_session.answer:
                outcome = "draw"
            else:
                outcome = "p1_win"
        elif match_session.p1_session.answer:
            outcome = "p1_win"
        elif match_session.p2_session.answer:
            outcome = "p2_win"
        else:
            outcome = "canceled"  
        
        await match_session.finish_match(outcome)
        
        await asyncio.sleep(2)
    
    except WebSocketDisconnect:
        if match_session.match_model and match_session.match_model.state == PvpMatchState.active:
            await match_session.finish_match("technical_error")
    except Exception as e:
        print(f"Error in active match: {e}")
        if match_session.match_model:
            await match_session.finish_match("technical_error")
    finally:
        await pvp_manager.remove_match(match_session.match_id)


@router.get("/queue-status")
async def get_queue_status(user: User = Depends(get_current_user)):
    user_id = str(user.id)
    
    if user_id in pvp_manager.player_queue:
        return {
            "status": "queued",
            "rating": user.elo_rating,
            "queue_size": len(pvp_manager.player_queue)
        }
    
    match_id = pvp_manager.get_player_match(user_id)
    if match_id:
        match_session = pvp_manager.get_match(match_id)
        if match_session:
            return {
                "status": "in_match",
                "match_id": match_id,
                "opponent_id": (match_session.p2_session.user_id 
                               if match_session.p2_session else None),
                "opponent_rating": (match_session.p2_session.rating 
                                   if match_session.p2_session else None)
            }
    
    return {"status": "idle", "rating": user.elo_rating}


@router.get("/matches/recent")
async def get_recent_matches(user: User = Depends(get_current_user), limit: int = 10):
    """Get user's recent PvP matches."""
    from app.data.models import PvpMatch
    
    user_id = str(user.id)
    
    matches = await PvpMatch.find(
        {
            "$or": [
                {"p1_user_id": user_id},
                {"p2_user_id": user_id}
            ]
        }
    ).sort([("started_at", -1)]).limit(limit).to_list()
    
    results = []
    for match in matches:
        is_p1 = match.p1_user_id == user_id
        opponent_id = match.p2_user_id if is_p1 else match.p1_user_id
        
        result = {
            "match_id": str(match.id),
            "opponent_id": opponent_id,
            "my_rating_before": match.p1_rating_start if is_p1 else match.p2_rating_start,
            "my_rating_delta": match.p1_rating_delta if is_p1 else match.p2_rating_delta,
            "outcome": match.outcome,
            "state": match.state,
            "started_at": match.started_at,
            "finished_at": match.finished_at,
        }
        results.append(result)
    
    return results


@router.get("/rating-leaderboard")
async def get_leaderboard(limit: int = 20):
    from app.data.models import User
    
    top_players = await User.find(
        User.is_blocked == False
    ).sort([("elo_rating", -1)]).limit(limit).to_list()
    
    leaderboard = [
        {
            "rank": idx + 1,
            "user_id": str(user.id),
            "email": user.email,
            "rating": user.elo_rating,
            "name": f"{user.first_name} {user.last_name}"
        }
        for idx, user in enumerate(top_players)
    ]
    
    return leaderboard
