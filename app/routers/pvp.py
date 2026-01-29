import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from app.data.models import User, PvpMatch, Task, PvpMatchState
from app.utils.security import get_current_user
from app.utils.pvp_manager import pvp_manager, MatchSession
from app.data import schemas

router = APIRouter(prefix="/pvp", tags=["PvP"])


@router.websocket("/")
async def websocket_pvp_match(websocket: WebSocket):
    """
    1) Client connects with JWT token (first message: {"type": "auth"|"bearer","token":"..."}).
    2) Player added to matchmaking queue.
    3) When paired: both players receive tasks (3 раунда).
    4) Players submit answers with submission IDs; duplicates не удваивают очки.
    5) Match result calculated (win/loss/draw).
    6) Elo ratings updated and persisted; aggregates updated.
    """

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

        user = await get_current_user(token)
        user_id = str(user.id)

        match_id = await pvp_manager.queue_player(user_id, user.elo_rating, websocket)
        if match_id:
            match_session = pvp_manager.get_match(match_id)
            await handle_active_match(match_session, user_id)
        else:
            await handle_queued_player(user_id, websocket, user.elo_rating)

    except WebSocketDisconnect:
        if user_id:
            await pvp_manager.remove_player(user_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
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


async def handle_active_match(match_session: MatchSession, current_user_id: str):
    # ждём второго игрока
    if not match_session.p2_session:
        if not await match_session.wait_for_both_players(timeout=30):
            return

    # верификация принадлежности
    if (current_user_id != match_session.p1_session.user_id and
            current_user_id != match_session.p2_session.user_id):
        await match_session.p1_session.websocket.send_json({
            "type": "error",
            "message": "User not part of this match"
        })
        return

    try:
        # Создаём запись матча (первый task проставим сразу после выборки)
        match_session.match_model = PvpMatch(
            p1_user_id=match_session.p1_session.user_id,
            p2_user_id=match_session.p2_session.user_id,
            p1_rating_start=match_session.p1_session.rating,
            p2_rating_start=match_session.p2_session.rating,
            task_id="",  # будет обновлён ниже
            state=PvpMatchState.active,
            started_at=datetime.utcnow(),
            p1=schemas.PvpSideState(user_id=match_session.p1_session.user_id),
            p2=schemas.PvpSideState(user_id=match_session.p2_session.user_id),
        )
        await match_session.match_model.save()

        match_session.p1_score = 0
        match_session.p2_score = 0
        rounds = 3
        answer_timeout = 300  # секунд

        for round_num in range(rounds):
            match_session.current_round = round_num + 1

            # Берём любую опубликованную задачу (при желании можно добавить случайность/фильтры)
            task = await Task.find_one(Task.is_published == True)
            if not task:
                await match_session.broadcast({"type": "error", "message": "No tasks available"})
                await match_session.finish_match("canceled")
                return

            match_session.task = task
            match_session.match_model.task_id = str(task.id)
            await match_session.match_model.save()

            # Сброс ответов
            match_session.p1_session.answer = None
            match_session.p1_session.counted_submission_id = None
            match_session.p2_session.answer = None
            match_session.p2_session.counted_submission_id = None

            # Отправляем задачу обоим
            await match_session.send_task()
            start_time = datetime.utcnow()

            while (datetime.utcnow() - start_time).total_seconds() < answer_timeout:
                # если оба успели ответить — идем к проверке
                if match_session.p1_session.answer and match_session.p2_session.answer:
                    break

                try:
                    websocket = (match_session.p1_session.websocket
                                 if current_user_id == match_session.p1_session.user_id
                                 else match_session.p2_session.websocket)
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

            # Проверяем корректность
            p1_ans = match_session.p1_session.answer
            p2_ans = match_session.p2_session.answer
            p1_correct = (p1_ans is not None and task.answer is not None and p1_ans == task.answer)
            p2_correct = (p2_ans is not None and task.answer is not None and p2_ans == task.answer)

            if p1_correct:
                match_session.p1_score += 1
            if p2_correct:
                match_session.p2_score += 1

            # короткая пауза между раундами
            await asyncio.sleep(0.5)

        # Итог по очкам
        if match_session.p1_score > match_session.p2_score:
            outcome = "p1_win"
        elif match_session.p2_score > match_session.p1_score:
            outcome = "p2_win"
        else:
            outcome = "draw"

        await match_session.finish_match(outcome)
        await asyncio.sleep(0.5)

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
    user_id = str(user.id)
    matches = await PvpMatch.find(
        {"$or": [{"p1_user_id": user_id}, {"p2_user_id": user_id}]}
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
            "outcome": (match.outcome.value if match.outcome else None),
            "state": match.state.value if hasattr(match.state, "value") else str(match.state),
            "started_at": match.started_at,
            "finished_at": match.finished_at,
        }
        results.append(result)
    return results


@router.get("/rating-leaderboard")
async def get_leaderboard(limit: int = 20):
    top_players = await User.find(User.is_blocked == False)\
        .sort([("elo_rating", -1)])\
        .limit(limit).to_list()
    leaderboard = [
        {
            "rank": idx + 1,
            "user_id": str(u.id),
            "email": u.email,
            "rating": u.elo_rating,
            "name": f"{u.first_name} {u.last_name}".strip()
        }
        for idx, u in enumerate(top_players)
    ]
    return leaderboard