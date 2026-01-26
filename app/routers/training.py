from fastapi import APIRouter, Depends, Query
from typing import List, Optional

from app.data.models import Task, User, UserStats
from app.data.schemas import TaskSchema, CheckAnswer, Theme, Difficulty
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
    
    if is_correct:
        user_stats = await UserStats.find_one({"user_id": str(current_user.id)})
        if user_stats:
            user_stats.correct += 1
            await user_stats.save()
        else:
            user_stats = UserStats(
                user_id=str(current_user.id),
                correct=1,
                attempts=0
            )
            await user_stats.save()
    
    return {
        "correct": is_correct
    }
 