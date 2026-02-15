from fastapi import APIRouter, Depends, status
from typing import Annotated, Dict, Literal
from app.data import schemas
from app.data.models import User, Admin
from app.utils.auth import create_user, authenticate_user
from app.utils.security import verify_password
from app.utils.exceptions import Error
from app.utils.security import verify_password, get_current_user, get_current_admin
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
    admin = await Admin.find_one(Admin.email == request.username)
    if admin and verify_password(request.password, admin.password_hash):

        token_expires = timedelta(minutes=60)
        token = await authenticate_user(data={"sub": request.username}, expires_delta=token_expires)

    else:
        
        user = await User.find_one(User.email == request.username)
        if not user or not verify_password(request.password, user.password_hash):
            raise Error.UNAUTHORIZED_INVALID

        token_expires = timedelta(minutes=1440)
        token = await authenticate_user(data={"sub": request.username}, expires_delta=token_expires)

    return schemas.Token(access_token=str(token), token_type="Bearer")


@router.get("/token")
async def get_user_by_token(current_user: User = Depends(get_current_user)) -> schemas.UserResponse:
    
    return schemas.UserResponse(
        id=str(current_user.id),
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        email=current_user.email,
        elo_rating=current_user.elo_rating,
        is_blocked=current_user.is_blocked
    )


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


@router.put("/{user_id}/block", status_code=status.HTTP_204_NO_CONTENT)
async def block_user(user_id: str, current_user: Admin = Depends(get_current_admin)):
    admin = await Admin.find_one(Admin.email == current_user.email)
    print(admin, current_user.email)
    if not admin:
        raise Error.NOT_ADMIN
    
    user = await User.get(user_id)
    if not user:
        raise Error.NOT_FOUND
    
    user.is_blocked = True
    await user.save()


@router.put("/{user_id}/role", status_code=status.HTTP_204_NO_CONTENT)
async def change_user_role(user_id: str, new_role: Literal["user", "admin"], current_user: Admin = Depends(get_current_admin)):
    admin = await Admin.find_one(Admin.email == current_user.email)
    if not admin:
        raise Error.NOT_ADMIN
    
    if new_role == "admin":
        user = await User.get(user_id)
        if not user:
            raise Error.NOT_FOUND
        
        new_admin = Admin(
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            password_hash=user.password_hash
        )
        await new_admin.insert()
        await user.delete()
    
    elif new_role == "user":
        admin_to_convert = await Admin.find_one(Admin.id == user_id)
        if not admin_to_convert:
            raise Error.NOT_FOUND
        
        new_user = User(
            first_name=admin_to_convert.first_name,
            last_name=admin_to_convert.last_name,
            email=admin_to_convert.email,
            password_hash=admin_to_convert.password_hash,
            is_blocked=False,
            elo_rating=1000
        )
        await new_user.insert()
        await admin_to_convert.delete() 
