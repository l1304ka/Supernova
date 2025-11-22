import json, re, random

# Load input
path="questions_optics_8.json"
with open(path,'r',encoding='utf-8') as f:
    data=json.load(f)

# Function to detect open
def is_open_answer(ans):
    # return bool(re.fullmatch(r"[А-Яа-яЁё]+", ans))
    return False

# Semantic distractors based on keywords
def generate_distractors(text, correct):
    q=text.lower()
    ds=[]
    if "линз" in q:
        ds=["Собирающая","Рассеивающая","Тонкая линза","Толстая линза"]
    elif "угол" in q or "падени" in q:
        ds=[
            "Угол между лучом и поверхностью",
            "Угол между отраженным лучом и нормалью",
            "Угол между преломленным лучом и поверхностью",
            "Угол между падающим лучом и зеркалом"
        ]
    elif "источник" in q:
        ds=["Лампа","Солнце","Свеча","Фонарик"]
    elif "изображен" in q:
        ds=[
            "Прямое и увеличенное",
            "Мнимое и уменьшенное",
            "Перевёрнутое и увеличенное",
            "Действительное и прямое"
        ]
    else:
        ds=[
            "Отражение света",
            "Поглощение света",
            "Рассеяние света",
            "Преломление света",
            "Интерференция света"
        ]
    ds=[d for d in ds if d.lower()!=correct.lower()]
    if len(ds)>=3:
        return random.sample(ds,3)
    # fill
    while len(ds)<3:
        ds.append("Неверный вариант")
    return ds[:3]

# Build output list
output=[]
for item in data:
    if item["model"]!="school.question":
        continue
    print(item)
    f=item["fields"]
    text=f["text"].strip()
    correct=f["correct_answer"].strip()
    openq=is_open_answer(correct)
    rec={
        "model": item["model"],
        "pk": item["pk"],
        "fields":{
            "subtopic": f["subtopic"],
            "text": text,
            "difficulty": f["difficulty"],
            "is_open": openq,
            "option_1": "",
            "option_2": "",
            "option_3": "",
            "option_4": "",
            "correct_answer": correct if openq else "1"
        }
    }
    if not openq:
        opts=[correct]
        ds=generate_distractors(text,correct)
        opts+=ds[:3]
        for i,opt in enumerate(opts,1):
            rec["fields"][f"option_{i}"]=opt
    output.append(rec)

json.dumps(output,ensure_ascii=False,indent=4)
# Save output
outpath="questions_optics_8_gen.json"
with open(outpath,'w',encoding='utf-8') as f:
    json.dump(output,f,ensure_ascii=False,indent=4)
