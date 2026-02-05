import csv
import io
import json
import httpx

from bson import ObjectId
from fastapi import APIRouter, Depends, Response, UploadFile, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
from app.data.schemas import TaskSchema, CheckAnswer, TaskSchemaRequest, Difficulty, Theme
from app.data.models import Task, Admin, User
from app.utils.security import get_current_user, get_current_admin
from app.utils.exceptions import Error
from app.integrations.gigachat_client import gigachat_client

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
    description="import tasks from json",
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
    '/upload/import/csv',
    description='import tasks from csv',
    responses={
        403: {"description": "Forbidden - You are not admin"}
    }
)
async def import_tasks(file: UploadFile, check_admin: Admin = Depends(get_current_admin)):
    try:
        content = await file.read()
        
        if content.startswith(b'\xef\xbb\xbf'):
            text = content.decode('utf-8-sig')
        else:
            text = content.decode('utf-8')
        
        first_line = text.split('\n')[0] if '\n' in text else text
        
        
        comma_count = first_line.count(',')
        semicolon_count = first_line.count(';')
        
        if semicolon_count > comma_count:
            delimiter = ';'
        elif comma_count > semicolon_count:
            delimiter = ','
        else:
            delimiter = ','  

        csv_file = io.StringIO(text)
        
        try:
            reader = csv.DictReader(csv_file, delimiter=delimiter)
        except csv.Error as e:
            raise Error.FILE_READ_ERROR
        
        results = {
            "created": 0,
            "updated": 0,
            "errors": []
        }
        
        for i, row in enumerate(reader, start=1):


            try:
                task_id = row.get('id', '').strip()
                
                task_data = {
                    "subject": row.get('subject', '').strip(),
                    "theme": row.get('theme', '').strip().lower(),
                    "title": row.get('title', '').strip(),
                    "task_text": row.get('task_text', '').strip(),
                    "hint": row.get('hint', '').strip(),
                    "answer": row.get('answer', '').strip(),
                }

                diff = row.get("difficulty", "лёгкий").strip().lower()
                if diff in ["лёгкий", "легкий", "easy"]:
                    task_data["difficulty"] = "лёгкий"
                elif diff in ["средний", "медиум", "medium"]:
                    task_data["difficulty"] = "средний"
                elif diff in ["hard", "тяжелый", "сложный"]:
                    task_data["difficulty"] = "сложный" 

                
                is_pub_str = row.get("is_published", "True").strip().lower()
                if is_pub_str in ["true", "yes", "да"]:
                    task_data["is_published"] = True
                elif is_pub_str in ["false", "no", "нет"]:
                    task_data["is_published"] = False
                else:
                    task_data["is_published"] = True  
                
                if task_id:

                    try:

                        object_id = ObjectId(task_id)

                        existing = await Task.find_one({"_id": object_id})
                        
                        if existing:
                            existing.subject = task_data["subject"]
                            existing.theme = task_data["theme"]
                            existing.difficulty = task_data["difficulty"]
                            existing.title = task_data["title"]
                            existing.task_text = task_data["task_text"]
                            existing.hint = task_data["hint"]
                            existing.answer = task_data["answer"]
                            existing.is_published = task_data["is_published"]
    
                            await existing.save()
                            results["updated"] += 1
                        else:

                            task = Task(
                                id=object_id,
                                **task_data
                            )
                            await task.insert()
                            results["created"] += 1
                            
                    except Exception as e:
                        results["errors"].append(f"Строка {i}: Ошибка '{str(e)}'")
                        
                else:
                    task = Task(**task_data)
                    await task.insert()
                    results["created"] += 1
                            
            except Exception as e:
                    results["errors"].append(f"Строка {i}: {str(e)}")
            
    except Exception as e:
        raise Error.FILE_READ_ERROR


    return {
        **results
    }
       

@router.post(
    '/{task_id}/check',
    description='Check user answer for task',
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
    description='export tasks into json',
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


@router.get(
    '/export/csv',
    description='export tasks into csv',
    responses={
        403: {"description": "Forbidden - You are not admin"}
    }
)
async def get_tasks_to_csv(check_admin: Admin = Depends(get_current_admin)):

    task_data = await Task.find_all().to_list() 
    if not task_data:
        raise Error.TASK_NOT_FOUND
    
    output = io.StringIO()

    writer = csv.writer(output, delimiter=';', lineterminator='\n')

    writer.writerow(["id", "subject", "theme", "difficulty", "title", "task_text", "hint", "answer", "is_published"])

    for task in task_data:
        writer.writerow([
            str(task.id),
            task.subject,
            task.theme,
            task.difficulty,
            task.title,
            task.task_text,
            task.hint,
            task.answer,
            task.is_published
            ])

    return Response(
        content=output.getvalue().encode('utf-8-sig'), 
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=tasks.csv",
            "Content-Type": "text/csv; charset=utf-8-sig"
        }
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


class GenerateTaskRequest(BaseModel):
    subject: str
    theme: Theme
    difficulty: Difficulty
    temperature: float | None = 0.7
    max_tokens: int | None = 700


@router.post(
    "/generate",
    response_model=TaskSchema,
    description="Сгенерировать одну задачу через GigaChat и сохранить в БД",
    responses={403: {"description": "Forbidden - You are not admin"}},
)
async def generate_task_via_gigachat(
    payload: GenerateTaskRequest,
    current_user: User = Depends(get_current_user),
) -> TaskSchema:
    try:
        title, task_text, hint, answer = await gigachat_client.generate_platform_task(
            subject=payload.subject,
            theme=payload.theme.value if hasattr(payload.theme, "value") else str(payload.theme),
            difficulty=payload.difficulty.value if hasattr(payload.difficulty, "value") else str(payload.difficulty),
            temperature=payload.temperature or 0.7,
            max_tokens=payload.max_tokens or 700,
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"GigaChat error: {e.response.text}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GigaChat integration failed: {e}") from e

    new_task = Task(
        subject=payload.subject,
        theme=payload.theme,
        difficulty=payload.difficulty,
        title=title,
        task_text=task_text,
        hint=hint,
        answer=answer,
        is_published=True,
    )
    await new_task.create()
    await new_task.save()

    return TaskSchema(
        id=str(new_task.id),
        subject=new_task.subject,
        theme=new_task.theme,
        difficulty=new_task.difficulty,
        title=new_task.title,
        task_text=new_task.task_text,
        hint=new_task.hint,
        answer=new_task.answer,
        is_published=new_task.is_published,
    )