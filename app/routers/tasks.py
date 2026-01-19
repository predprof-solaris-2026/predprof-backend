import json
from fastapi import APIRouter, Depends, Response, UploadFile
from app.data.schemas import TaskSchema
from app.data.models import Task
from app.utils.security import get_current_user
from app.utils.exceptions import Error

router = APIRouter(prefix="/tasks", tags=["Tasks"])







# POST-requests






@router.post(
        '/upload',
        description="making tasks (withowt admin check yet)",
        responses={
            
        }
)
async def post_tasks(data: TaskSchema) -> TaskSchema:


    #проверка на админа будет потом
    task_exists = Task.find_one(Task.title == data.title)
    # if task_exists:
    #     raise Error.TITLE_EXISTS
    # я пока убрал, сомнительно, тайтлы могут повторяться

    new_task = Task(
        subject = data.subject,
        theme = data.theme,
        difficulty = data.difficulty,
        title = data.title,
        task_text = data.task_text,  
        hint = data.hint,               
        is_published = True
    )
    
    await new_task.create()
    await new_task.save()

    return TaskSchema(
        subject = data.subject,
        theme = data.theme,
        difficulty = data.difficulty,
        title = data.title,
        task_text = data.task_text,  
        hint = data.hint,               
        is_published = True
    )
    


@router.post(
        '/upload/import/json',
         description="import files from json",
         responses={
             
         }
)



async def post_tasks(file: UploadFile):


    #проверка на админа будет потом

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
            is_published = True
            )
            task = Task.find_one(Task.title == task_field["title"])
            # if task:
            #     raise Error.TITLE_EXISTS

            await new_task.create()
            await new_task.save()
            all_tasks_added.append(TaskSchema(
                subject = task_field["subject"],
                theme = task_field["theme"],
                difficulty = task_field["difficulty"],
                title = task_field["title"],
                task_text = task_field["task_text"],  
                hint = task_field["hint"],               
                is_published = True
            ))
        return all_tasks_added
        
    except Exception as e:
        raise Error.FILE_READ_ERROR
        







# PATCH-requests








@router.patch(
        '/{title}',
        description='edit task',
        responses={

        }
)
async def update_task(request: TaskSchema, title: str ):
    task = await Task.find_one(Task.title == title)
    task_exists = Task.find_one(Task.title == request.title)
    # if task_exists:
    #     raise Error.TITLE_EXISTS
    task.subject = request.subject
    task.theme = request.theme
    task.difficulty  = request.difficulty
    task.title = request.title
    task.task_text = request.task_text
    task.hint =   request.hint
    task.is_published = request.is_published

    await task.save()
    return task







# GET-requests







@router.get(
    '/',
    description="get all tasks",
    responses={

    }
)
async def get_tasks():
    tasks = await Task.find_all().to_list()
    return tasks




@router.get(
    '/{title}',
    description="get definite task",
    responses={

    }
)
async def get_definite_task(title:str):
    task = await Task.find_one(Task.title == title)
    return task



@router.get(
        '/export',
        description='export files into json',
        responses={

        }
)
async def get_tasks_to_json():
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
    
