import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
import httpx
from datetime import timezone

from app.data.models import User, PvpMatch, Task, PvpMatchState
from app.utils.security import get_current_user
from app.utils.pvp_manager import pvp_manager, MatchSession
from app.data import schemas

import asyncio
import uuid
from datetime import datetime

router = APIRouter(prefix="/pvp", tags=["PvP"])


@router.websocket("/")
async def websocket_pvp_match(websocket: WebSocket):
    await websocket.accept()
    user = None
    user_id = None
    try:
        token = None
        msg = await websocket.receive_json()
        if msg.get("type") in ("auth", "bearer"):
            token = msg.get("token")
        if not token:
            await websocket.send_json({"type": "error", "message": "Missing authentication token"})
            await websocket.close(code=1008)
            return

        try:
            from app.main import app as fastapi_app
            async with httpx.AsyncClient(app=fastapi_app, base_url="http://testserver") as client:
                resp = await client.post("/api/auth/validate-token", json={"token": token}, timeout=5.0)
        except Exception:
            await websocket.send_json({"type": "error", "message": "Authentication service unreachable"})
            await websocket.close(code=1011)
            return

        if resp.status_code != 200:
            await websocket.send_json({"type": "error", "message": "Invalid authentication token"})
            await websocket.close(code=1008)
            return

        data = resp.json()
        sub = data.get("sub")
        exp = data.get("exp")
        if not sub or exp is None:
            await websocket.send_json({"type": "error", "message": "Invalid token payload"})
            await websocket.close(code=1008)
            return

        if datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(tz=timezone.utc):
            await websocket.send_json({"type": "error", "message": "Token expired"})
            await websocket.close(code=1008)
            return

        user = await User.find_one(User.email == sub, fetch_links=True)
        if not user:
            await websocket.send_json({"type": "error", "message": "User not found"})
            await websocket.close(code=1008)
            return

        user_id = str(user.id)

        match_id = await pvp_manager.queue_player(user_id, user.elo_rating, websocket)
        if match_id:
            match_session = pvp_manager.get_match(match_id)
            await handle_active_match(match_session, user_id)
        else:
            await handle_queued_player(user_id, websocket, user.elo_rating)
            
        await websocket.close(code=1011)
    except WebSocketDisconnect as e:
        if user_id:
            await pvp_manager.remove_player(user_id)
        await websocket.close(code=1008)
    except Exception as e:
        try:
            await websocket.close(code=1011)
        except Exception:
            pass


async def handle_queued_player(user_id: str, websocket: WebSocket, rating: int):
    await websocket.send_json({
        "type": "queued",
        "message": "Waiting for opponent...",
        "rating": rating
    })
    while True:
        try:
            msg = await asyncio.wait_for(websocket.receive_json(), timeout=1.0)
        except asyncio.TimeoutError:
            msg = None

        if msg is not None and msg.get("type") == "cancel":
            await pvp_manager.remove_player(user_id)
            await websocket.send_json({"type": "canceled", "message": "Removed from queue"})
            break

        match_id = pvp_manager.get_player_match(user_id)
        if match_id:
            match_session = pvp_manager.get_match(match_id)
            await handle_active_match(match_session, user_id)
            break

async def run_game_cycle(match_session):
    try:
        match_session.match_model = PvpMatch(
            p1_user_id=match_session.p1_session.user_id,
            p2_user_id=match_session.p2_session.user_id,
            p1_rating_start=match_session.p1_session.rating,
            p2_rating_start=match_session.p2_session.rating,
            task_id="",
            state=PvpMatchState.active,
            started_at=datetime.utcnow(),
            p1=schemas.PvpSideState(user_id=match_session.p1_session.user_id),
            p2=schemas.PvpSideState(user_id=match_session.p2_session.user_id),
        )
        await match_session.match_model.save()

        match_session.p1_score = 0
        match_session.p2_score = 0
        answer_timeout = 300

        success, err_msg = await match_session.prepare_tasks()
        if not success:
            await match_session.broadcast({"type": "error", "message": err_msg})
            await match_session.finish_match("canceled")
            return

        for round_num in range(1, match_session.rounds_total + 1):
            match_session.current_round = round_num
            
            task = match_session.selected_tasks[round_num - 1]
            match_session.task = task
            match_session.match_model.task_id = str(task.id)
            await match_session.match_model.save()

            match_session.p1_session.answer = None
            match_session.p2_session.answer = None

            await match_session.send_task()
            start_time = datetime.utcnow()

            while (datetime.utcnow() - start_time).total_seconds() < answer_timeout:
                if match_session.p1_session.answer and match_session.p2_session.answer:
                    break
                await asyncio.sleep(0.1) 
            
            p1_ans = match_session.p1_session.answer
            p2_ans = match_session.p2_session.answer
            
            correct_ans = str(task.answer).strip() if task.answer is not None else None
            
            p1_correct = (p1_ans is not None and correct_ans is not None and str(p1_ans).strip() == correct_ans)
            p2_correct = (p2_ans is not None and correct_ans is not None and str(p2_ans).strip() == correct_ans)

            if p1_correct:
                match_session.p1_score += 1
            if p2_correct:
                match_session.p2_score += 1

            await match_session.broadcast({
                "type": "round_result",
                "p1_correct": p1_correct,
                "p2_correct": p2_correct,
                "p1_score": match_session.p1_score,
                "p2_score": match_session.p2_score,
                "correct_answer": correct_ans
            })

            # await asyncio.sleep(2.0) 

        if match_session.p1_score > match_session.p2_score:
            outcome = "p1_win"
        elif match_session.p2_score > match_session.p1_score:
            outcome = "p2_win"
        else:
            outcome = "draw"

        await match_session.finish_match(outcome)
        # await asyncio.sleep(0.2)

    except Exception as e:
        await match_session.finish_match("technical_error")


async def handle_active_match(match_session: MatchSession, current_user_id: str):
    if not match_session.p2_session:
        if not await match_session.wait_for_both_players(timeout=30):
            return
    if (current_user_id != match_session.p1_session.user_id
            and current_user_id != match_session.p2_session.user_id):
        await match_session.p1_session.websocket.send_json({
            "type": "error", "message": "User not part of this match"
        })
        return

    current_websocket = (
        match_session.p1_session.websocket
        if current_user_id == match_session.p1_session.user_id
        else match_session.p2_session.websocket
    )
    
    if not hasattr(match_session, "game_task") or match_session.game_task is None:
        match_session.game_task = asyncio.create_task(run_game_cycle(match_session))

    try:
        while True:
            # msg = await current_websocket.receive_json()
            try:
                msg = await asyncio.wait_for(current_websocket.receive_json(), timeout=2.0)
            except asyncio.TimeoutError:
                continue

            if msg.get("type") == "answer":
                submission_id = msg.get("submission_id", str(uuid.uuid4()))
                answer = msg.get("answer", "")
                
                counted = match_session.handle_answer_submission(current_user_id, answer, submission_id)
                
                await current_websocket.send_json({
                    "type": "answer_received",
                    "submission_id": submission_id,
                    "counted": counted,
                    "message": "Answer recorded" if counted else "Answer rejected (duplicate)"
                })
                await match_session.broadcast_state()

            elif msg.get("type") == "disconnect":
                await match_session.finish_match("technical_error")
                break

    except asyncio.CancelledError:
        pass
    except Exception as e:
        await match_session.finish_match("technical_error")
    finally:
        await current_websocket.close(code=1000)


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
    user_id = str(user.id)
    matches = await PvpMatch.find(
        {"$or": [{"p1_user_id": user_id}, {"p2_user_id": user_id}]}
    ).sort([("started_at", -1)]).limit(limit).to_list()

    results = []
    for match in matches:
        is_p1 = match.p1_user_id == user_id
        opponent_id = match.p2_user_id if is_p1 else match.p1_user_id
        results.append({
            "match_id": str(match.id),
            "opponent_id": opponent_id,
            "my_rating_before": match.p1_rating_start if is_p1 else match.p2_rating_start,
            "my_rating_delta": match.p1_rating_delta if is_p1 else match.p2_rating_delta,
            "outcome": (match.outcome.value if match.outcome else None),
            "state": match.state.value if hasattr(match.state, "value") else str(match.state),
            "started_at": match.started_at,
            "finished_at": match.finished_at,
        })
    return results


@router.get("/rating-leaderboard")
async def get_leaderboard(limit: int = 20):
    top_players = await User.find(User.is_blocked == False).sort([("elo_rating", -1)]).limit(limit).to_list()
    leaderboard = [
        {
            "rank": idx + 1,
            "user_id": str(user.id),
            "email": user.email,
            "rating": user.elo_rating,
            "name": f"{user.first_name} {user.last_name}".strip(),
        }
        for idx, user in enumerate(top_players)
    ]
    return leaderboard