[![Build and Deploy Backend](https://github.com/predprof-solaris-2026/predprof-backend/actions/workflows/deploy.yml/badge.svg?branch=main)](https://github.com/predprof-solaris-2026/predprof-backend/actions/workflows/deploy.yml)

<h1 align="center">Приложение с web-интерфейсом для подготовки к олимпиадам.</a> 
<h3 align="center">Предоставляет
различные уровни доступа для пользователей и администраторов,
предоставляет банк заданий, тренировки, пвп, просмотр личного и общего рейтинга, а
также просмотр статистики для администратора по использованию веб-приложения. </h3>

[Видео работы продукта](https://)

### Необходимо для дальнейшей работы

- Python 3.10 или выше
- [pip](https://pip.pypa.io/en/stable/)
- [Virtualenv](https://pypi.org/project/virtualenv/)

### Установка

1. **Склонируйте репозиторий:**

    ```shell
    git clone https://github.com/predprof-solaris-2026/predprof-backend
    ```

2. **Создайте и активируйте виртуальное окружение (рекомендовано):**
   
    ```shell
    python -m venv venv
    venv/Scripts/activate
    ```

4. **Установите зависимости:**
   
    ```shell
    pip install -r requirements.txt
    ```
6. **Создайте .env в корне проекта:**

    ```
    DATABASE_URL = "mongodb://localhost:27017/Predprof"
    ADMIN_TOKEN = "ADMIN_TOKEN"
    ALGORITHM = "HS256"
    SECURITY_KEY = "SECURITY_KEY"
    SECURITY_KEY_USER = "SECURITY_KEY_USER"
    ACCESS_TOKEN_EXPIRE_MINUTES=99999
    ENVIRONMENT="test"
    ```
    
7. **Запустите сервер (1 способ):**

     ```shell
    docker compose up -d
    ```
7. **Запустите сервер (2 способ):**

     ```shell
    uvicorn app.main:app
    ```

    [Репозиторий фронтенда](https://github.com/predprof-solaris-2026/predprof-frontend)
