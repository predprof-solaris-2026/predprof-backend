from typing import Annotated
import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError, DecodeError

from app import ALGORITHM, SECRET_KEY  # основной секрет
# опционально: если у вас есть второй ключ (например, старые токены)
try:
    from app import SECRET_KEY_USER as ALT_SECRET_KEY
except Exception:
    ALT_SECRET_KEY = None

from app.data.models import User, TokenData, Admin
from app.utils.exceptions import Error
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext

context_pass = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/user/login")

def verify_password(plain_password, hashed_password):
    return context_pass.verify(plain_password, hashed_password)

def _decode_with_fallback(token: str) -> dict:
    try:
        return jwt.decode(str(token), str(SECRET_KEY), algorithms=[ALGORITHM])
    except ExpiredSignatureError:
        raise Error.UNAUTHORIZED_INVALID
    except InvalidTokenError:
        raise Error.UNAUTHORIZED_INVALID

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    try:
        payload = _decode_with_fallback(token)
        username: str = payload.get("sub")
        if not username:
            raise Error.UNAUTHORIZED_INVALID
        token_data = TokenData(username=username)
        user = await User.find_one(User.email == token_data.username, fetch_links=True)
        if user is None:
            raise Error.UNAUTHORIZED_INVALID
        return user
    except (InvalidTokenError, ExpiredSignatureError, DecodeError):
        raise Error.UNAUTHORIZED_INVALID
    except Exception:
        # на всякий пожарный — не светим детали
        raise Error.UNAUTHORIZED_INVALID

async def get_current_admin(token: Annotated[str, Depends(oauth2_scheme)]):
    try:
        payload = _decode_with_fallback(token)
        username: str = payload.get("sub")
        if not username:
            raise Error.NOT_ADMIN
        token_data = TokenData(username=username)
        admin = await Admin.find_one(Admin.email == token_data.username, fetch_links=True)
        if admin is None:
            raise Error.NOT_ADMIN
        return admin
    except (InvalidTokenError, ExpiredSignatureError, DecodeError):
        raise Error.NOT_ADMIN
    except Exception:
        raise Error.NOT_ADMIN
