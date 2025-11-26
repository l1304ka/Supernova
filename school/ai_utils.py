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
    Ты — учитель физики 8 класса, который пишет строгие, ясные и короткие задачи без лишних слов.

    Сгенерируй {tasks_count} НОВЫХ ЗАДАЧ по теме: "{topic_name}"
    с учётом уровня ученика:
    - результат на тесте по теме: {score_percent}%
    - ориентировочная сложность: {difficulty_hint}

    ТРЕБОВАНИЯ:
    1. Формат — классическая школьная задача (1 короткий абзац, без художественного текста).
    2. Без обращений к ученику. Только формальное условие.
    3. В задаче должны быть числа и требоваться вычисление.
    4. Ответ — только число без единиц.
    5. Решение обязательно оформлять ПОШАГОВО, на отдельных строках.
    6. В ход решения обязательно включай математические выражения в формате LaTeX.
    - Для встроенных формул используй: $ формула $
    - Для крупных формул используй: $$ формула $$
    
    ТРЕБОВАНИЯ К ОФОРМЛЕНИЮ РЕШЕНИЯ:
    1. Каждый шаг решения должен идти в отдельном абзаце:  
       <p class="solution-step">Шаг X: ...</p>
    
    2. Если в шаге есть формула — пиши её ТОЛЬКО в формате LaTeX,  
       и обязательно оборачивай в HTML-блок:
    
       <div class="math-block">
       $$ ... формула ... $$
       </div>
    
    3. Если формула короткая — используй inline-формат:
       $ ... $
    
    4. Между шагами делай перенос строки (но не используй <br>).
    
    ПРИМЕР ПРАВИЛЬНОГО ОФОРМЛЕНИЯ РЕШЕНИЯ:
    <p class="solution-step">Шаг 1: Используем формулу тонкой линзы.</p>
    <div class="math-block">
    $$ \\frac{{1}}{{F}} = \\frac{{1}}{{d_o}} + \\frac{{1}}{{d_i}} $$
    </div>
    
    <p class="solution-step">Шаг 2: Выразим d_i.</p>
    <div class="math-block">
    $$ d_i = \\frac{{1}}{{ \\frac{{1}}{{F}} - \\frac{{1}}{{d_o}} }} $$
    </div>
    
    <p class="solution-step">Шаг 3: Подставим значения и посчитаем.</p>
    <div class="math-block">
    $$ d_i = \\frac{{1}}{{ \\frac{{1}}{{20}} - \\frac{{1}}{{30}} }} = 60 $$
    </div>
    
    <p class="solution-step">Ответ: 60</p>


    ПРИМЕР ФОРМАТА (не использовать как основу условий):
    [
      {{
        "text": "Лучи света падают на зеркало под углом 30°. Найдите угол отражения.",
        "solution": "Шаг 1: По закону отражения угол падения равен углу отражения.\nШаг 2: Значит угол отражения = 30.\nОтвет: 30",
        "answer": "30"
      }},
      {{
        "text": "Предмет находится в 40 см от линзы. Увеличение изображения равно -0.5. Найдите расстояние до изображения.",
        "solution": "Шаг 1: Формула увеличения: m = -d_изобр / d_предм.\nШаг 2: d_изобр = -m * d_предм = 0.5 * 40.\nШаг 3: d_изобр = 20.\nОтвет: 20",
        "answer": "20"
      }}
    ]

    СФОРМИРУЙ СТРОГО ВАЛИДНЫЙ JSON:
    [
      {{
        "text": "...",
        "solution": "...",  
        "answer": "..."
      }},
      ...
    ]

    Количество объектов — ровно {tasks_count}.
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
