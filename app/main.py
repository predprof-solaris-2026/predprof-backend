from beanie import init_beanie, Document, UnionDoc
from fastapi import FastAPI, APIRouter
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi.middleware.cors import CORSMiddleware

from app import MONGO_DSN, ENVIRONMENT, projectConfig
from app.routers import user, tasks, pvp, training, stats, rating, auth

from app.data import models as _models 

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
        description=projectConfig.__description__,
        docs_url="/api/docs",
        openapi_url="/api/v1/openapi.json"
    )

api_router = APIRouter(prefix="/api")

api_router.include_router(user.router)
api_router.include_router(tasks.router)
api_router.include_router(pvp.router)
api_router.include_router(auth.router)
api_router.include_router(training.router)
api_router.include_router(stats.router)
api_router.include_router(rating.router)
app.include_router(api_router)

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
