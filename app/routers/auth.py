from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError, DecodeError

from app import SECRET_KEY, ALGORITHM
from app.data.models import Admin, User

router = APIRouter(prefix="/auth", tags=["Auth"])


class TokenRequest(BaseModel):
    token: str


@router.post("/validate-token")
async def validate_token(body: TokenRequest):
    token = body.token
    try:
        payload = jwt.decode(str(token), str(SECRET_KEY), algorithms=[ALGORITHM])
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    except (InvalidTokenError, DecodeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    user = await User.find_one(User.email == username, fetch_links=True)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return {"valid": True, "user_id": str(user.id), "sub": username, "exp": payload.get("exp")}


@router.post("/role")
async def check_role(body: TokenRequest):
    token = body.token
    try:
        payload = jwt.decode(str(token), str(SECRET_KEY), algorithms=[ALGORITHM])
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    except (InvalidTokenError, DecodeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    admin = await Admin.find_one(Admin.email == username, fetch_links=True)
    if not admin:
        return {"role": "user"}

    return {"role": "admin"}
