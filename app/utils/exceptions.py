from fastapi import HTTPException, status


class Error(Exception):
    
    USER_NOT_FOUND = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="User not found."
    )
    
    LOGIN_EXISTS = HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Login already exists."
    )
    
    UNAUTHORIZED_INVALID = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect login or password."
    )
    
    HISTORY_NOT_FOUND = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="History not found."
    )
    FILE_READ_ERROR = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Cannot read the file."
    )
    TITLE_EXISTS = HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Task with this title already exists"
    )
