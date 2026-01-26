from fastapi import APIRouter, Depends
from typing import Annotated, Dict
from app.data import schemas
from app.data.models import User
from app.utils.auth import create_user, authenticate_user
from app.utils.security import verify_password
from app.utils.exceptions import Error
from app.utils.security import verify_password, get_current_user
from datetime import timedelta
from fastapi.security import OAuth2PasswordRequestForm


router = APIRouter(prefix="/user", tags=["User"])

@router.post("/create")
async def registration_user(request: schemas.UserSchema) -> schemas.UserLogIn:
    await create_user(request)
    token_expires = timedelta(minutes=1440)
    token = await authenticate_user(data={"sub": request.email}, expires_delta=token_expires)
    return schemas.UserLogIn(
        user_token=str(token)
    )


@router.post("/login")
async def log_in_user(request: Annotated[OAuth2PasswordRequestForm, Depends()]) -> schemas.Token:
    user = await User.find_one(User.email == request.username)
    if not user or not verify_password(request.password, user.password_hash):
        raise Error.UNAUTHORIZED_INVALID

    token_expires = timedelta(minutes=1440)
    token = await authenticate_user(data={"sub": request.username}, expires_delta=token_expires)

    return schemas.Token(access_token=token, token_type="bearer")


@router.get("/{user_id}")
async def get_user_by_id(user_id: str) -> schemas.UserResponse:
    user = await User.get(user_id)
    if not user:
        raise Error.NOT_FOUND
    
    return schemas.UserResponse(
        id=str(user.id),
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        elo_rating=user.elo_rating,
        is_blocked=user.is_blocked
    )


@router.get("")
async def get_all_users() -> list[schemas.UserResponse]:
    users = await User.find_all().to_list()
    
    return [
        schemas.UserResponse(
            id=str(user.id),
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            elo_rating=user.elo_rating,
            is_blocked=user.is_blocked
        )
        for user in users
    ]
