from fastapi import APIRouter, Depends, Query
from typing import List, Optional

from datetime import datetime

from app.data.models import Task, User, UserStats, UserAggregateStats
from app.data.schemas import TaskSchema, CheckAnswer, Theme, Difficulty, ThemeStat
from app.utils.security import get_current_user
from app.utils.exceptions import Error

router = APIRouter(prefix="/training", tags=["Training"])


@router.get('/',response_model=List[TaskSchema])
async def get_tasks(
    subject: Optional[str] = Query(None),
    theme: Optional[Theme] = Query(None),
    difficulty: Optional[Difficulty] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0)
) -> List[TaskSchema]:
    query_filters = {"is_published": True}
    
    if subject:
        query_filters["subject"] = subject
    if theme:
        query_filters["theme"] = theme
    if difficulty:
        query_filters["difficulty"] = difficulty
    
    tasks = await Task.find(query_filters).skip(skip).limit(limit).to_list()
    
    return [
        TaskSchema(
            id=str(task.id),
            subject=task.subject,
            theme=task.theme,
            difficulty=task.difficulty,
            title=task.title,
            task_text=task.task_text,
            hint=None,
            answer=None,
            is_published=task.is_published
        )
        for task in tasks
    ]


@router.get('/task/{task_id}/hint')
async def get_task_hint(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    try:
        task = await Task.get(task_id)
    except Exception:
        raise Error.TASK_NOT_FOUND
    
    if not task or not task.is_published:
        raise Error.TASK_NOT_FOUND
    
    return {
        "hint": task.hint
    }


@router.post('/task/{task_id}/check')
async def check_answer(
    task_id: str,
    payload: CheckAnswer,
    current_user: User = Depends(get_current_user)
):
    try:
        task = await Task.get(task_id)
    except Exception:
        raise Error.TASK_NOT_FOUND
    if not task or not task.is_published:
        raise Error.TASK_NOT_FOUND

    correct_answer = task.answer
    user_answer = payload.answer
    is_correct = False
    if correct_answer is not None:
        is_correct = str(user_answer).strip().lower() == str(correct_answer).strip().lower()

    uid = str(current_user.id)
    theme_key = task.theme

    user_stats = await UserStats.find_one({"user_id": uid})
    if not user_stats:
        user_stats = UserStats(user_id=uid)

    user_stats.attempts += 1
    if is_correct:
        user_stats.correct += 1

    tstat = user_stats.by_theme.get(theme_key, ThemeStat())
    tstat.attempts += 1
    if is_correct:
        tstat.correct += 1

    if payload.elapsed_ms is not None:
        prev_avg = user_stats.avg_time_ms or 0.0
        n_prev = user_stats.attempts - 1
        user_stats.avg_time_ms = ((prev_avg * n_prev) + payload.elapsed_ms) / user_stats.attempts

        prev_t_avg = tstat.avg_time_ms or 0.0
        n_prev_t = tstat.attempts - 1
        tstat.avg_time_ms = ((prev_t_avg * n_prev_t) + payload.elapsed_ms) / tstat.attempts

    user_stats.by_theme[theme_key] = tstat
    await user_stats.save()

    agg = await UserAggregateStats.find_one({"user_id": uid})
    if not agg:
        agg = UserAggregateStats(user_id=uid)

    agg.training.attempts += 1
    if is_correct:
        agg.training.correct += 1
    else:
        agg.training.incorrect += 1

    atstat = agg.training.by_theme.get(theme_key, ThemeStat())
    atstat.attempts += 1
    if is_correct:
        atstat.correct += 1

    if payload.elapsed_ms is not None:
        prev_t_avg = atstat.avg_time_ms or 0.0
        n_prev_t = atstat.attempts - 1
        atstat.avg_time_ms = ((prev_t_avg * n_prev_t) + payload.elapsed_ms) / atstat.attempts

    agg.training.by_theme[theme_key] = atstat
    agg.updated_at = datetime.utcnow()
    await agg.save()

    return {"correct": is_correct}