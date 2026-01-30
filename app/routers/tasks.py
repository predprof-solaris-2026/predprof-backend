import json
from fastapi import APIRouter, Depends, Response, UploadFile
from pydantic import BaseModel
from typing import Dict, Any
from app.data.schemas import TaskSchema, CheckAnswer, TaskSchemaRequest
from app.data.models import Task, Admin
from app.utils.security import get_current_user, get_current_admin
from app.utils.exceptions import Error

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post(
    '/upload',
    description="making tasks (withowt admin check yet)",
    responses={
        403: {"description": "Forbidden - You are not admin"}
    }
)
async def post_tasks(data: TaskSchemaRequest, check_admin: Admin = Depends(get_current_admin)) -> TaskSchema:
    

    new_task = Task(
        subject = data.subject,
        theme = data.theme,
        difficulty = data.difficulty,
        title = data.title,
        task_text = data.task_text,  
        hint = data.hint,               
        answer = data.answer,
        is_published = True
    )
    
    await new_task.create()
    await new_task.save()
    task_id = str(new_task.id)

    return TaskSchema(
        id= task_id,
        subject = data.subject,
        theme = data.theme,
        difficulty = data.difficulty,
        title = data.title,
        task_text = data.task_text,  
        hint = data.hint,               
        answer = data.answer,
        is_published = True
    )
    







@router.post(
    '/upload/import/json',
    description="import files from json",
    responses={
        403: {"description": "Forbidden - You are not admin"}
    }
)
async def post_tasks(file: UploadFile, check_admin: Admin = Depends(get_current_admin)):
    try:

        content = await file.read()
        
        json_file = json.loads(content.decode('utf-8'))
        all_tasks_added = []
        for task_field in json_file["tasks"]:

            new_task = Task(
            subject = task_field["subject"],
            theme = task_field["theme"],
            difficulty = task_field["difficulty"],
            title = task_field["title"],
            task_text = task_field["task_text"],  
            hint = task_field["hint"],               
            answer = task_field.get("answer"),
            is_published = True
            )

            await new_task.create()
            await new_task.save()
            all_tasks_added.append(TaskSchema(
                subject = task_field["subject"],
                theme = task_field["theme"],
                difficulty = task_field["difficulty"],
                title = task_field["title"],
                task_text = task_field["task_text"],  
                hint = task_field["hint"],               
                answer = task_field.get("answer"),
                is_published = True
            ))
        return all_tasks_added
        
    except Exception as e:
        raise Error.FILE_READ_ERROR
        

@router.post(
        
        
    '/{task_id}/check',
    description='Check user answer for task',
    responses={
              

    }
)
async def check_task(task_id: str, payload: CheckAnswer):
    task = await Task.get(task_id)
    if not task:
        raise Error.TASK_NOT_FOUND
    correct_answer = task.answer
    user_answer = payload.answer
    is_correct = False
    if correct_answer is not None:
        is_correct = str(user_answer).strip().lower() == str(correct_answer).strip().lower()

    return {
        "correct": is_correct,
        "correct_answer": correct_answer
    }



@router.patch(
    '/{task_id}',
    description='edit task by id',
    responses={
        403: {"description": "Forbidden - You are not admin"}
    }
)
async def update_task(request: TaskSchema, task_id: str, check_admin: Admin = Depends(get_current_admin) ):
    task = await Task.get(task_id)

    task.subject = request.subject
    task.theme = request.theme
    task.difficulty  = request.difficulty
    task.title = request.title
    task.task_text = request.task_text
    task.hint =   request.hint
    task.answer = request.answer
    task.is_published = request.is_published

    await task.save()
    return task


@router.get(
    '/',
    description="get all tasks",
    responses={

    }
)
async def get_tasks():
    tasks = await Task.find_all().to_list()
    tasks_list = []
    for t in tasks:
        d: Dict[str, Any] = t.model_dump()
        if 'answer' in d:
            d.pop('answer')
        tasks_list.append(d)
    return tasks_list









@router.get(
    '/get/{task_id}',
    description="get definite task by id",
    responses={

    }
)
async def get_definite_task(task_id: str):
    task = await Task.get(task_id)
    if not task:
        raise Error.TASK_NOT_FOUND
    task_dict: Dict[str, Any] = task.model_dump()
    if 'answer' in task_dict:
        task_dict.pop('answer')
    return task_dict








@router.get(
    '/export',
    description='export files into json',
    responses={
        403: {"description": "Forbidden - You are not admin"}
    }
)
async def get_tasks_to_json(check_admin: Admin = Depends(get_current_admin)):
    task_data = await Task.find_all().to_list() 
    task_dict = [task.model_dump() for task in task_data]
    export_tasks = {
        "tasks": task_dict 
    }
 
    json_str = json.dumps(export_tasks, indent= 2, ensure_ascii=False)
    return Response(
        content=json_str,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=users.json"}
    )


@router.delete(
    '/{task_id}',
    description='Delete tasks by id',
    responses={
        403: {"description": "Forbidden - You are not admin"}
    }
)
async def delete_task(task_id:str, check_admin: Admin = Depends(get_current_admin)):
    task = await Task.get(task_id)

    if not task:
        raise Error.TASK_NOT_FOUND
    await task.delete()

    return {"message": "Task was deleted succesfully"}
