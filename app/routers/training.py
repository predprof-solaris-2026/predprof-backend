from fastapi import APIRouter, Depends, Query
from typing import List, Optional

from datetime import datetime

from app.data.models import Task, User, UserStats, UserAggregateStats
from app.data.schemas import TaskSchema, CheckAnswer, Theme, Difficulty, ThemeStat, PersonalRecommendation, AdaptivePlan, HintResponse, CheckResponse, PlanResponse, TaskRecommendation, ThemeResponse
from app.utils.security import get_current_user
from app.utils.exceptions import Error
from app.utils.adaptive_learning import (
    individual_plan,
    recommended_task,
    theme_difficulty
)

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


@router.get('/task/{task_id}/hint', response_model=HintResponse)
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
    
    uid = str(current_user.id)
    user_stats = await UserStats.find_one({"user_id": uid})
    if not user_stats:
        user_stats = UserStats(user_id=uid)
    
    user_stats.hints_used = (user_stats.hints_used or 0) + 1
    await user_stats.save()
    
    return HintResponse(hint=task.hint)


@router.post('/task/{task_id}/check', response_model=CheckResponse)
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
        correct_answer_normalized = str(correct_answer).strip().lower().replace(',', '.')
        user_answer_normalized = str(user_answer).strip().lower().replace(',', '.')
        is_correct = user_answer_normalized == correct_answer_normalized

    uid = str(current_user.id)
    theme_key = str(task.theme)

    user_stats = await UserStats.find_one({"user_id": uid})
    if not user_stats:
        user_stats = UserStats(user_id=uid)

    user_stats.attempts += 1
    if is_correct:
        user_stats.correct += 1
    else:
        user_stats.incorrect += 1

    tstat = user_stats.by_theme.get(theme_key, ThemeStat())
    tstat.attempts += 1
    if is_correct:
        tstat.correct += 1
    else:
        tstat.incorrect += 1

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

    return CheckResponse(correct=is_correct)


@router.get('/plan', response_model=PlanResponse)
async def get_adaptive_plan(current_user: User = Depends(get_current_user)):
    user_id = str(current_user.id)
    plan = await individual_plan(user_id)
    if not plan:
        return PlanResponse(recommendations=[])
    return PlanResponse(recommendations=plan.recommendations)


@router.get('/recommended-task', response_model=Optional[TaskRecommendation])
async def get_next_task_recommendation(current_user: User = Depends(get_current_user)):
    user_id = str(current_user.id)
    task_rec = await recommended_task(user_id)
    
    if not task_rec:
        return TaskRecommendation(
            id=None,
            theme=None,
            difficulty=None,
            reason="Чтобы получить рекомендации решите пару задач в тренировочном режиме"
        )
    
    return TaskRecommendation(**task_rec)


@router.get('/theme/{theme}', response_model=ThemeResponse)
async def get_theme_analysis(
    theme: Theme,
    current_user: User = Depends(get_current_user)
):
    user_id = str(current_user.id)
    
    difficulty_stats = await theme_difficulty(user_id, theme.value)
    
    recommendations = [
        {
            "difficulty": "лёгкий",
            "recommendation": "Хороший уровень для начала" if difficulty_stats["easy"] >= 0.5 else "Нужна практика"
        },
        {
            "difficulty": "средний",
            "recommendation": "Переходите сюда, когда будете уверены в лёгких задачах" if difficulty_stats["easy"] >= 0.65 else "Подождите, сначала укрепите основы"
        },
        {
            "difficulty": "сложный",
            "recommendation": "Готовьтесь к экзамену" if difficulty_stats["hard"] >= 0.7 else "Подождите, сначала укрепите основы"
        }
    ]
    
    return ThemeResponse(theme=str(theme.value), recommendations=[
        {
            "difficulty": rec["difficulty"],
            "recommendation": rec["recommendation"]
        }
        for rec in recommendations
    ])