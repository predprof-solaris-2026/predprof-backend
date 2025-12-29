import json
from fastapi import APIRouter, Depends, Response
from app.data.schemas import TaskSchema
from app.data.models import Task
from app.utils.security import get_current_user
from app.utils.exceptions import Error

router = APIRouter(prefix="/tasks", tags=["Tasks"])




@router.post(
        '/upload',
        description="making tasks (withowt admin check yet)",
        responses={
            
        }
)
async def post_tasks(data: TaskSchema) -> TaskSchema:


    #проверка на админа будет потом



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
    


'''

@router.post(
        '/upload/import',
         description="import files from json and csv",
         responses={
             
         }
)
async def post_tasks():


    #проверка на админа будет потом

    

    return 200
    

'''


@router.get('/export')
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
    
