# app/integrations/gigachat_client.py
from __future__ import annotations

import os
import time
import uuid
import json
import asyncio
from typing import Optional, Tuple, Dict, Any

import httpx


def _get_bool_env(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "y")


class GigaChatClient:
    """
    Клиент GigaChat с ленивым обновлением токена:
    - Токен хранится в памяти процесса и обновляется по требованию.
    - Обновление токена защищено asyncio.Lock (чтобы не было гонок).
    - Поддерживается кастомный корневой сертификат через env (по требованию GigaChat).
    """

    def __init__(self) -> None:
        # Конфиги из окружения (не меняем ваши текущие файлы, читаем env прямо здесь)
        self.auth_url = os.getenv("GIGACHAT_AUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
        self.api_base = os.getenv("GIGACHAT_API_BASE", "https://gigachat.devices.sberbank.ru/api/v1")
        self.basic_key = os.getenv("GIGACHAT_AUTH_BASIC_KEY")  # Authorization key (Basic)
        self.scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self.model = os.getenv("GIGACHAT_MODEL", "GigaChat-2-Pro")

        # Кастомный корневой сертификат НУЦ Минцифры: путь к .crt/.pem; если не задан — используем системный стор
        ca_cert_path = os.getenv("GIGACHAT_CA_CERT")  # например: "/etc/ssl/certs/MinCifra_Root_CA.pem"
        self._verify: bool | str = ca_cert_path if ca_cert_path else True

        # Таймауты
        self.request_timeout_sec = float(os.getenv("GIGACHAT_TIMEOUT", "30"))

        # Токен + защита
        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0  # epoch seconds
        self._lock = asyncio.Lock()

    async def _fetch_token(self) -> None:
        """
        Получает токен через POST /api/v2/oauth с Basic-авторизацией.
        Документация: https://ngw.devices.sberbank.ru:9443/api/v2/oauth
        """
        if not self.basic_key:
            raise RuntimeError("GIGACHAT_AUTH_BASIC_KEY не задан (Authorization key для Basic).")

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {self.basic_key}",
        }
        data = {"scope": self.scope}

        async with httpx.AsyncClient(timeout=self.request_timeout_sec, verify=self._verify) as client:
            resp = await client.post(self.auth_url, headers=headers, data=data)
            resp.raise_for_status()
            payload = resp.json()

        # По доке приходит expires_at (unix timestamp в миллисекундах)
        access_token = payload.get("access_token")
        expires_at_ms = payload.get("expires_at")
        if not access_token or not expires_at_ms:
            raise RuntimeError(f"Некорректный ответ при получении токена: {payload}")

        # Берём небольшой запас (-60 секунд), чтобы не попасть на «вот-вот истечёт»
        self._access_token = access_token
        self._expires_at = (int(expires_at_ms) / 1000.0) - 60.0

    async def _get_token(self) -> str:
        """
        Возвращает актуальный токен. Обновляет его по необходимости.
        Двойная проверка + lock для защиты от гонок.
        """
        now = time.time()
        if self._access_token and now < self._expires_at:
            return self._access_token

        async with self._lock:
            now = time.time()
            if self._access_token and now < self._expires_at:
                return self._access_token
            await self._fetch_token()
            return self._access_token  # type: ignore

    async def list_models(self) -> Dict[str, Any]:
        """
        Тестовый вызов: GET /api/v1/models — проверка доступности API.
        """
        token = await self._get_token()
        headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
        url = f"{self.api_base}/models"
        async with httpx.AsyncClient(timeout=self.request_timeout_sec, verify=self._verify) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def chat_completions(self, messages: list[dict], *, model: Optional[str] = None,
                               max_tokens: int = 512, temperature: float = 0.7,
                               n: int = 1, stream: bool = False, repetition_penalty: float = 1.0,
                               update_interval: int = 0) -> Dict[str, Any]:
        """
        Вызов POST /api/v1/chat/completions (OpenAI-совместимый формат).
        Документация: https://gigachat.devices.sberbank.ru/api/v1/chat/completions
        """
        token = await self._get_token()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        payload = {
            "model": model or self.model,
            "messages": messages,
            "n": n,
            "stream": stream,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "repetition_penalty": repetition_penalty,
            "update_interval": update_interval,
        }

        url = f"{self.api_base}/chat/completions"
        async with httpx.AsyncClient(timeout=self.request_timeout_sec, verify=self._verify) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _extract_text_from_choice(payload: Dict[str, Any]) -> str:
        # Ожидаем OpenAI-стиль: choices[0].message.content
        try:
            return payload["choices"][0]["message"]["content"]
        except Exception:
            return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _try_extract_json(text: str) -> Dict[str, Any] | None:
        # Убираем возможные ```json ... ```
        s = text.strip()
        if s.startswith("```"):
            s = s.strip("`").strip()
            # Если первая строка была "json", уберём её
            if s.lower().startswith("json"):
                s = s[4:].strip()
        try:
            return json.loads(s)
        except Exception:
            return None

    async def generate_platform_task(self, subject: str, theme: str, difficulty: str,
                                     *, temperature: float = 0.7, max_tokens: int = 700
                                     ) -> Tuple[str, str, Optional[str], Optional[str]]:
        """
        Генерация задачи для платформы.
        Возвращает кортеж: (title, task_text, hint, answer).
        """
        sys_msg = {
            "role": "system",
            "content": (
                "Ты генератор олимпиадных задач для школьников. "
                "Отвечай строго в формате JSON без лишнего текста, без комментариев и без маркдауна. "
                "Схема: {\"title\": str, \"task_text\": str, \"hint\": str|null, \"answer\": str|null}. "
                "Язык: русский."
            ),
        }
        user_msg = {
            "role": "user",
            "content": (
                f"Предмет: {subject}\n"
                f"Тема: {theme}\n"
                f"Сложность: {difficulty}\n\n"
                "Сгенерируй одну задачу. "
                "Подбери ёмкий заголовок (title), чёткое условие (task_text), "
                "небольшую подсказку (hint) при необходимости и краткий ответ (answer). "
                "Верни ТОЛЬКО JSON по схеме, ничего кроме JSON."
            ),
        }

        raw = await self.chat_completions(
            [sys_msg, user_msg],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        content = self._extract_text_from_choice(raw)
        data = self._try_extract_json(content)

        # Фоллбек, если модель выдала невалидный JSON
        title = f"AI: {subject} / {theme} / {difficulty}"
        task_text: str = content
        hint: Optional[str] = None
        answer: Optional[str] = None

        if isinstance(data, dict):
            title = str(data.get("title") or title)
            task_text = str(data.get("task_text") or task_text)
            hint_val = data.get("hint")
            answer_val = data.get("answer")
            hint = None if hint_val in (None, "", "null", "-") else str(hint_val)
            answer = None if answer_val in (None, "", "null", "-") else str(answer_val)

        return title, task_text, hint, answer


# Глобальный singleton-инстанс
gigachat_client = GigaChatClient()