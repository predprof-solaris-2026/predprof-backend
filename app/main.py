from beanie import init_beanie, Document, UnionDoc
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi.middleware.cors import CORSMiddleware

from app import MONGO_DSN, ENVIRONMENT, projectConfig
from app.routers import user, tasks
if ENVIRONMENT == "prod":
    app = FastAPI(
        title=projectConfig.__projname__,
        version=projectConfig.__version__,
        description=projectConfig.__description__,
        docs_url=None
    )

else:
    app = FastAPI(
        title=projectConfig.__projname__,
        version=projectConfig.__version__,
        description=projectConfig.__description__
    )


app.include_router(user.router)
app.include_router(tasks.router)
@app.on_event('startup')
async def startup_event():
    client = AsyncIOMotorClient(MONGO_DSN)

    await init_beanie(
        database=client['Predprof'],
        document_models=Document.__subclasses__() + UnionDoc.__subclasses__()
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
