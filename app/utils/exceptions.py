from fastapi import HTTPException, status


class Error(Exception):
    
    USER_NOT_FOUND = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Пользователь не найден"
    )
    
    LOGIN_EXISTS = HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Пользователь с такой почтой уже существует"
    )
    
    UNAUTHORIZED_INVALID = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Некорректная почта или пароль"
    )
    
    HISTORY_NOT_FOUND = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="История не найдена"
    )
    FILE_READ_ERROR = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Файл не прочитан"
    )
    TASK_NOT_FOUND = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Задания не найдены"
    )
    NOT_ADMIN = HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="У вас нет доступа к этому ресурсу"
    )
    BLOCKED = HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Вы заблокированы"
    )