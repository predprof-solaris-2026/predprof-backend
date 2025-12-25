<h1 align="center">Приложение с web-интерфейсом для учета
школьного спортивного инвентаря.</a> 
<h3 align="center">Предоставляет
различные уровни доступа для пользователей и администраторов,
позволяет вести учет инвентаря, распределять его среди пользователей, а
также планировать закупки. </h3>

[Видео работы продукта](https://vkvideo.ru/video484917838_456239292?list=ln-WmHCggx05o04z8V3gQ)

### Необходимо для дальнейшей работы

- Python 3.8 или выше
- [pip](https://pip.pypa.io/en/stable/)
- [Virtualenv](https://pypi.org/project/virtualenv/)

### Установка

1. **Склонируйте репозиторий:**

    ```shell
    git clone https://github.com/Ania-Krivs/predprof-sports-equipment.git
    ```

2. **Перейдите в каталог проекта:**

    ```shell
    cd backend
    ```

3. **Создать и активировать виртуальное окружение (рекомендовано):**

    ```shell
    app/venv/Scripts/activate
    ```
4. **Установите зависимости:**

    ```shell
    pip install -r requirements.txt
    ```
5. **Измените /backend/.env:**

    ```
    DATABASE_URL = "mongodb://localhost:27017/Predprof"
    ADMIN_TOKEN = "ADMIN_TOKEN"
    ALGORITHM = "ALGORITHM(HS256)"
    SECURITY_KEY = "SECURITY_KEY"
    SECURITY_KEY_USER = "SECURITY_KEY_USER"
    ACCESS_TOKEN_EXPIRE_MINUTES=99999

    ACCESS_TOKEN_EXPIRE_MINUTES_REDIS = 99999
    REDIS_HOST = "localhost"
    REDIS_PORT = 6379

    ENVIRONMENT="test"
    ```
6. **Запустите сервер:**

    ```shell
    uvicorn app.main:app
    ```
7. **Перейдите к папку frontend:**

    ```shell
    cd frontend
    ```
8. **Измените .env.local:**

    ```
    VITE_API_URL="YOUR_BACKEND_URL"
    ```
9. **Установите зависимости:**

    ```shell
    npm install
    ```
10. **Запустите сайт:**

    ```shell
    npm run dev
    ```
