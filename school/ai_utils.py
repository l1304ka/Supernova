# school/ai_utils.py
import json
from google import genai
from django.conf import settings


def generate_homework_tasks_gemini(topic_name: str,
                                   tasks_count: int,
                                   difficulty_hint: str,
                                   score_percent: int) -> list[dict]:
    """
    Возвращает список словарей:
    [
      {"text": "...", "solution": "...", "answer": "42"},
      ...
    ]
    """

    # Инициализация клиента
    client = genai.Client(api_key=settings.GENAI_API_KEY)

    prompt = f"""
Ты — строгий, но добрый учитель физики 8 класса.

Сгенерируй {tasks_count} НОВЫХ ЗАДАЧ по теме: "{topic_name}".

Уровень ученика:
- его результат на тесте по этой теме: {score_percent}%,
- ориентировочная сложность заданий: {difficulty_hint}.

ТРЕБОВАНИЯ К ЗАДАЧАМ:
1. Это обычные текстовые задачи (не тест, не выбор ответа).
2. Ответ ВСЕГДА только ЧИСЛО без единиц измерения и без текста.
   Примеры корректных ответов: "5", "3.2", "-1.5", "0".
   Примеры НЕКОРРЕКТНЫХ ответов: "5 м", "5 метров", "выпуклая", "да", "нет".
3. Внутри условия можно использовать любые данные, но решение должно быть однозначным.
4. Каждая задача должна подходить для школьника 8 класса (Россия), без высшей математики.
5. Обязательно добавляй ПОДРОБНЫЙ ХОД РЕШЕНИЯ, понятный ученику.

ФОРМАТ ОТВЕТА:
Верни строго валидный JSON без комментариев, без пояснений и без лишнего текста.
Структура:

[
  {{
    "text": "условие задачи (1–3 абзаца, на русском)",
    "solution": "подробный ход решения, пошагово, на русском",
    "answer": "ЧИСЛО_БЕЗ_ЕДИНИЦ"
  }},
  ...
]

Количество элементов в массиве должно быть ровно {tasks_count}.
"""

    # Запрос к модели
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    raw = response.text.strip()

    # Удаляем ```json код-блоки, если появились
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[-1]
        if raw.lower().startswith("json"):
            raw = raw[4:]

    # Иногда модель добавляет текст до или после JSON → очищаем
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # fallback – вытаскиваем всё между [ и ]
        start = raw.find("[")
        end = raw.rfind("]") + 1
        cleaned = raw[start:end]
        data = json.loads(cleaned)

    tasks = []
    for item in data:
        tasks.append({
            "text": item["text"],
            "solution": item["solution"],
            "answer": str(item["answer"]).strip(),
        })

    return tasks
