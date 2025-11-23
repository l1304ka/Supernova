import random
from urllib import request

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.timezone import now

from administrator.views import superuser_required
from .ai_utils import generate_homework_tasks_gemini
from .models import Test, TestResult, Student, Topic, Lesson, Subject, AssignedTopic, Question, StudentAnswer, Teacher, \
    SchoolClass, Homework, HomeworkTask


@login_required
def index(request):
    user = request.user

    # ─────────────────────────────────────────────
    # БЛОК ДЛЯ УЧИТЕЛЯ
    # ─────────────────────────────────────────────
    if hasattr(user, 'teacher'):
        teacher = user.teacher
        classes = teacher.classes.all()
        subjects = teacher.subjects.all()
        students = Student.objects.filter(classes__in=classes).distinct()

        stats = []
        for s in students:
            results = TestResult.objects.filter(student=s)
            avg_grade = round(sum(r.grade for r in results) / len(results), 2) if results else None

            # first 5 results
            # results = results.order_by("-completed_at")[:5]
            stats.append({
                "student": s,
                "results": results,
                "avg_grade": avg_grade,
            })

        return render(request, "teacher_dashboard.html", {
            "teacher": teacher,
            "classes": classes,
            "subjects": subjects,
            "stats": stats,
        })

    # ─────────────────────────────────────────────
    # БЛОК ДЛЯ УЧЕНИКА
    # ─────────────────────────────────────────────
    elif hasattr(user, 'student'):
        student = user.student
        classes = student.classes.all()

        # Все назначенные темы
        assigned_topics = AssignedTopic.objects.filter(
            school_class__in=classes,
            is_active=True
        ).distinct()

        # Завершённые тесты
        results = TestResult.objects.filter(
            student=student
        ).select_related("assigned_topic").order_by("-completed_at")

        finished_ids = set(results.values_list("assigned_topic_id", flat=True))

        # ─────────────────────────────────────────────
        # ЗАГРУЖАЕМ ВСЕ НЕЗАВЕРШЁННЫЕ ТЕСТЫ
        # ─────────────────────────────────────────────
        adaptive_tests = request.session.get("adaptive_tests", {})

        unfinished_tests = []
        for assigned_id_str in adaptive_tests.keys():
            try:
                unfinished_tests.append(
                    AssignedTopic.objects.get(id=int(assigned_id_str))
                )
            except AssignedTopic.DoesNotExist:
                pass

        unfinished_ids = {u.id for u in unfinished_tests}

        # ─────────────────────────────────────────────
        # ДОСТУПНЫЕ ТЕСТЫ
        # исключаем завершённые и незавершённые
        # ─────────────────────────────────────────────
        available_tests = assigned_topics.exclude(id__in=finished_ids | unfinished_ids)

        last_result = results.first() if results else None

        results = results.order_by("-completed_at")[:5]

        return render(request, "index.html", {
            "results": results,
            "unfinished_tests": unfinished_tests,
            "available_tests": available_tests,
            "last_result": last_result,
        })

    # ─────────────────────────────────────────────
    # НЕ студента и не учитель
    # ─────────────────────────────────────────────
    else:
        return render(request, "index.html", {
            "available_tests": [],
            "results": []
        })


@login_required
def assign_homework(request):
    teacher = request.user.teacher

    if request.method == "POST":
        class_id = request.POST.get("class_id")
        topic_id = request.POST.get("topic_id")
        title = request.POST.get("title", "")

        AssignedTopic.objects.create(
            title=title,
            school_class_id=class_id,
            topic_id=topic_id,
            assigned_by=teacher
        )
        return redirect("index")

    classes = teacher.classes.all()
    subjects = teacher.subjects.all()
    return render(request, "assign_homework.html", {
        "classes": classes,
        "subjects": subjects,
    })


def test_detail(request, test_id):
    student = Student.objects.get(user=request.user)
    test = get_object_or_404(Test, id=test_id)

    # проверка: если уже есть результат — не даем повторно проходить
    existing_result = TestResult.objects.filter(student=student, test=test).first()
    if existing_result:
        return redirect("test_result", test_id=test.id)

    questions = test.questions.all()

    if request.method == "POST":
        correct_count = 0
        for q in questions:
            answer = request.POST.get(f"q{q.id}", "").strip().lower()
            if answer == q.correct_answer.strip().lower():
                correct_count += 1

        total = len(questions)
        score = int((correct_count / total) * 100) if total > 0 else 0

        # Оценка 2–5 по процентам
        if score < 40:
            grade = 2
        elif score < 60:
            grade = 3
        elif score < 85:
            grade = 4
        else:
            grade = 5

        TestResult.objects.create(
            student=student,
            test=test,
            assigned_topic=test.assigned_topic,  # ← ВАЖНО: сохраняем конкретное назначение!
            score=score,
            grade=grade
        )


        return redirect("test_result", test_id=test.id)

    return render(request, "test_detail.html", {"test": test, "questions": questions})


def test_result(request, test_id):
    student = Student.objects.get(user=request.user)
    result = get_object_or_404(TestResult, student=student, test_id=test_id)
    return render(request, "test_result.html", {"result": result})


@login_required
def get_topics_by_subject(request):
    """Возвращает темы по выбранному предмету"""
    subject_id = request.GET.get("subject_id")
    if not subject_id:
        return JsonResponse({"error": "no subject_id"}, status=400)

    print(subject_id)
    try:
        subject = Subject.objects.get(id=subject_id)
    except Subject.DoesNotExist:
        return JsonResponse({"error": "subject not found"}, status=404)

    topics = subject.topics.all().values("id", "name")
    return JsonResponse({"topics": list(topics)})


def shuffle_options(question):
    opts = []
    if question.option_1:
        opts.append(("1", question.option_1))
    if question.option_2:
        opts.append(("2", question.option_2))
    if question.option_3:
        opts.append(("3", question.option_3))
    if question.option_4:
        opts.append(("4", question.option_4))

    random.shuffle(opts)
    return opts


@login_required
def adaptive_test(request, test_id):
    student = request.user.student
    assigned = get_object_or_404(AssignedTopic, id=test_id, is_active=True)

    # Все активные адаптивные тесты в сессии
    tests = request.session.get("adaptive_tests", {})

    # Данные конкретного теста
    data = tests.get(str(test_id))

    # ─────────────────────────────────────────────
    # ИНИЦИАЛИЗАЦИЯ ТЕСТА (GET)
    # ─────────────────────────────────────────────
    if request.method == "GET":

        if data is None:
            # Создаём новую структуру
            data = {
                "step": 1,
                "difficulty": "medium",
                "correct": 0,
                "wrong": 0,
                "asked": [],
                "answers": {}  # question_id → {"answer": "...", "is_correct": bool}
            }
            tests[str(test_id)] = data
            request.session["adaptive_tests"] = tests

        # Если уже был задан вопрос — показываем его
        if data["asked"]:
            q = Question.objects.get(id=data["asked"][-1])

            # перемешиваем варианты (однакj сохраняем порядок оригинальных id!!)
            options = []
            if q.option_1: options.append(("1", q.option_1))
            if q.option_2: options.append(("2", q.option_2))
            if q.option_3: options.append(("3", q.option_3))
            if q.option_4: options.append(("4", q.option_4))

            random.shuffle(options)

            return render(request, "adaptive_test.html", {
                "step": data["step"],
                "total_questions": assigned.question_count,
                "question": q,
                "difficulty": data["difficulty"],
                "assigned": assigned,
                "options": options
            })

        # Генерируем первый вопрос
        qs = Question.objects.filter(
            subtopic__topics=assigned.topic,
            difficulty="medium"
        )
        if not qs.exists():
            qs = Question.objects.filter(subtopic__topics=assigned.topic)

        q = random.choice(list(qs))
        data["asked"].append(q.id)
        tests[str(test_id)] = data
        request.session["adaptive_tests"] = tests

        # перемешиваем варианты
        options = []
        if q.option_1: options.append(("1", q.option_1))
        if q.option_2: options.append(("2", q.option_2))
        if q.option_3: options.append(("3", q.option_3))
        if q.option_4: options.append(("4", q.option_4))
        random.shuffle(options)

        return render(request, "adaptive_test.html", {
            "step": data["step"],
            "total_questions": assigned.question_count,
            "question": q,
            "difficulty": data["difficulty"],
            "assigned": assigned,
            "options": options
        })

    # ─────────────────────────────────────────────
    # POST — ОБРАБОТКА ОТВЕТА
    # ─────────────────────────────────────────────

    if data is None:
        return redirect("index")

    qid = int(request.POST.get("question_id"))
    question = get_object_or_404(Question, id=qid)

    answer = request.POST.get("answer", "").strip().lower()
    correct = question.correct_answer.strip().lower()
    is_correct = (answer == correct)

    # сохраняем ответ в сессию полностью!
    data["answers"][str(qid)] = {
        "answer": answer,
        "is_correct": is_correct
    }

    # обновляем статистику сложности
    if is_correct:
        data["correct"] += 1
        data["difficulty"] = increase_difficulty(data["difficulty"])
    else:
        data["wrong"] += 1
        data["difficulty"] = decrease_difficulty(data["difficulty"])

    data["step"] += 1
    tests[str(test_id)] = data
    request.session["adaptive_tests"] = tests

    # ─────────────────────────────────────────────
    # ЗАВЕРШЕНИЕ ТЕСТА
    # ─────────────────────────────────────────────

    if data["step"] > assigned.question_count:
        total = data["correct"] + data["wrong"]
        pct = int((data["correct"] / total) * 100) if total else 0

        grade = (
            2 if pct < 40 else
            3 if pct < 60 else
            4 if pct < 85 else
            5
        )

        lesson = assigned.topic.lessons.first()

        final_test = Test.objects.create(
            lesson=lesson,
            title=f"Адаптивный тест по теме: {assigned.topic.name}",
            date_available=now().date(),
            assigned_topic=assigned,
            topic=assigned.topic,
            maximin_questions=assigned.question_count
        )

        result = TestResult.objects.create(
            student=student,
            test=final_test,
            assigned_topic=assigned,
            score=pct,
            grade=grade
        )

        # Сохраняем ВСЕ ответы
        for qid in data["asked"]:
            q = Question.objects.get(id=qid)
            saved = data["answers"].get(str(qid))

            if saved:
                StudentAnswer.objects.create(
                    result=result,
                    question=q,
                    given_answer=saved["answer"],
                    is_correct=saved["is_correct"]
                )

        # удаляем только этот тест из сессии
        tests.pop(str(test_id), None)
        request.session["adaptive_tests"] = tests

        return redirect("test_result_detail", result.id)

    # ─────────────────────────────────────────────
    # ГЕНЕРАЦИЯ НОВОГО ВОПРОСА
    # ─────────────────────────────────────────────

    next_qs = Question.objects.filter(
        subtopic__topics=assigned.topic,
        difficulty=data["difficulty"]
    ).exclude(id__in=data["asked"])

    if not next_qs.exists():
        next_qs = Question.objects.filter(
            subtopic__topics=assigned.topic
        ).exclude(id__in=data["asked"])

    q = random.choice(list(next_qs))
    data["asked"].append(q.id)
    tests[str(test_id)] = data
    request.session["adaptive_tests"] = tests

    # перемешиваем варианты ответов
    options = []
    if q.option_1: options.append(("1", q.option_1))
    if q.option_2: options.append(("2", q.option_2))
    if q.option_3: options.append(("3", q.option_3))
    if q.option_4: options.append(("4", q.option_4))
    random.shuffle(options)

    return render(request, "adaptive_test.html", {
        "step": data["step"],
        "total_questions": assigned.question_count,
        "question": q,
        "difficulty": data["difficulty"],
        "assigned": assigned,
        "options": options
    })


# =================================================
#         ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =================================================

def increase_difficulty(d):
    order = ["very_easy", "easy", "medium", "hard", "very_hard"]
    i = order.index(d)
    return order[min(i + 1, 4)]


def decrease_difficulty(d):
    order = ["very_easy", "easy", "medium", "hard", "very_hard"]
    i = order.index(d)
    return order[max(i - 1, 0)]



@login_required
def student_results(request):
    student = request.user.student
    results = TestResult.objects.filter(student=student).order_by("-completed_at")
    return render(request, "student_results.html", {"results": results})


@login_required
def test_result_detail(request, result_id):
    result = get_object_or_404(TestResult, id=result_id, student__user=request.user)
    answers = result.answers.select_related("question")

    total = answers.count()
    correct = answers.filter(is_correct=True).count()

    return render(request, "test_result_detail.html", {
        "result": result,
        "answers": answers,
        "total": total,
        "correct": correct,
        "percent": int((correct / total) * 100) if total else 0,
    })


@superuser_required
def subject_list(request):
    return render(request, "adminpanel/subject_list.html", {
        "section": "subjects",
        "subjects": Subject.objects.all()
    })


@superuser_required
def add_subject(request):
    if request.method == "POST":
        name = request.POST["name"]
        Subject.objects.create(name=name)
        return redirect("admin_subjects")

    return render(request, "adminpanel/add_subject.html", {"section": "subjects"})


@superuser_required
def edit_subject(request, id):
    subject = get_object_or_404(Subject, id=id)

    if request.method == "POST":
        subject.name = request.POST["name"]
        subject.save()
        return redirect("admin_subjects")

    return render(request, "adminpanel/edit_subject.html", {
        "section": "subjects",
        "subject": subject
    })


@superuser_required
def delete_subject(request, id):
    subject = get_object_or_404(Subject, id=id)
    subject.delete()
    return redirect("admin_subjects")


@superuser_required
def assign_teachers(request, id):
    school_class = get_object_or_404(SchoolClass, id=id)
    all_teachers = Teacher.objects.all()

    if request.method == "POST":
        selected = request.POST.getlist("teachers")
        school_class.teachers.set(selected)
        return redirect("admin_classes")

    return render(request, "adminpanel/assign_teachers.html", {
        "section": "classes",
        "school_class": school_class,
        "all_teachers": all_teachers
    })


@superuser_required
def assign_students(request, id):
    school_class = get_object_or_404(SchoolClass, id=id)
    all_students = Student.objects.all()

    if request.method == "POST":
        selected = request.POST.getlist("students")
        school_class.students.set(selected)
        return redirect("admin_classes")

    return render(request, "adminpanel/assign_students.html", {
        "section": "classes",
        "school_class": school_class,
        "all_students": all_students
    })

def superuser_required(view_func):
    return user_passes_test(lambda u: u.is_superuser, login_url="/account/login/")(view_func)

@login_required
def class_journal(request, class_id):
    school_class = get_object_or_404(SchoolClass, id=class_id)
    students = school_class.students.all()

    rows = []
    for s in students:
        results = TestResult.objects.filter(student=s).order_by("completed_at")
        rows.append({
            "student": s,
            "results": results,
            "last": results.last() if results else None,
            "avg": round(sum(r.grade for r in results) / len(results), 2) if results else None,
        })
    print(rows)


    return render(request, "class_journal.html", {
        "class": school_class,
        "rows": rows,
    })


@login_required
def assign_homework_class(request, class_id):
    teacher = request.user.teacher
    school_class = get_object_or_404(SchoolClass, id=class_id)

    subjects = teacher.subjects.all()

    if request.method == "POST":
        topic_id = request.POST.get("topic_id")
        title = request.POST.get("title", "")
        question_count = int(request.POST.get("question_count", "0"))

        AssignedTopic.objects.create(
            title=title,
            school_class=school_class,
            topic_id=topic_id,
            assigned_by=teacher,
            question_count=question_count
        )

        return redirect("class_journal", class_id=class_id)

    return render(request, "assign_homework_class.html", {
        "school_class": school_class,
        "subjects": subjects,
    })

@login_required
def teacher_student_detail(request, id):
    student = get_object_or_404(Student, id=id)

    results = TestResult.objects.filter(student=student).order_by("-completed_at")

    return render(request, "teacher_student_detail.html", {
        "student": student,
        "results": results,
    })

@login_required
def class_tests(request, class_id):
    school_class = get_object_or_404(SchoolClass, id=class_id)

    # назначенные темы
    assigned = AssignedTopic.objects.filter(school_class=school_class)

    # все тесты, которые когда-либо проходили ученики класса
    test_results = TestResult.objects.filter(
        student__classes=school_class
    ).select_related("test", "student")

    # сгруппировать тесты
    tests = {}
    for r in test_results:
        t = r.test
        if t.id not in tests:
            tests[t.id] = {
                "test": t,
                "results": [],
                "students_count": 0
            }
        tests[t.id]["results"].append(r)

    for t in tests.values():
        t["students_count"] = len(t["results"])

    return render(request, "class_tests.html", {
        "school_class": school_class,
        "assigned": assigned,
        "tests": tests.values(),
    })


@login_required
def delete_test(request, test_id):
    test = get_object_or_404(Test, id=test_id)
    test.delete()
    return redirect(request.META.get("HTTP_REFERER", "/"))


@login_required
def delete_assigned_topic(request, aid):
    assigned = get_object_or_404(AssignedTopic, id=aid)
    assigned.delete()
    return redirect(request.META.get("HTTP_REFERER", "/"))


@login_required
def generate_homework(request, result_id):
    """Создать ИИ-домашку по конкретному результату теста."""
    result = get_object_or_404(TestResult, id=result_id, student__user=request.user)

    # если уже есть ДЗ — просто переходим к нему
    if hasattr(result, "homework"):
        return redirect("homework_detail", homework_id=result.homework.id)

    assigned = result.assigned_topic  # ты уже сохраняешь assigned_topic в TestResult
    student = result.student

    # сколько задач по умолчанию берём из назначенной темы, иначе 3
    tasks_count = 3

    # подсказка для сложности
    if result.score >= 85:
        diff_hint = "чуть выше среднего уровня, можно включить 1–2 сложные задачи"
    elif result.score >= 60:
        diff_hint = "средний уровень"
    else:
        diff_hint = "чуть проще среднего уровня, чтобы закрепить базу"

    # генерим задачи через Gemini
    tasks_data = generate_homework_tasks_gemini(
        topic_name=assigned.topic.name,
        tasks_count=tasks_count,
        difficulty_hint=diff_hint,
        score_percent=result.score,
    )

    # создаём Homework + задачи
    hw = Homework.objects.create(
        student=student,
        topic=assigned,
        test_result=result,
        tasks_count=len(tasks_data),
    )

    for i, t in enumerate(tasks_data, start=1):
        HomeworkTask.objects.create(
            homework=hw,
            order=i,
            text=t["text"],
            solution=t["solution"],
            correct_answer=t["answer"],
        )

    return redirect("homework_detail", homework_id=hw.id)

@login_required
def homework_detail(request, homework_id):
    hw = get_object_or_404(
        Homework,
        id=homework_id,
        student__user=request.user
    )
    tasks = list(hw.tasks.order_by("order"))

    if request.method == "POST":
        # ученик отправил ответы
        for task in tasks:
            field_name = f"task_{task.id}"
            ans = request.POST.get(field_name, "").strip()

            if ans != "":
                task.student_answer = ans
                # сравниваем как числа с небольшой поблажкой
                try:
                    correct = float(str(task.correct_answer).replace(",", "."))
                    given = float(ans.replace(",", "."))
                    task.is_correct = abs(correct - given) < 1e-6
                except ValueError:
                    task.is_correct = False
            else:
                task.student_answer = ""
                task.is_correct = False

            task.save()

        hw.is_checked = True
        hw.save()

        return redirect("homework_detail", homework_id=hw.id)

    # количество верных для отображения
    total = len(tasks)
    correct = len([t for t in tasks if t.is_correct])

    return render(request, "homework_detail.html", {
        "homework": hw,
        "tasks": tasks,
        "total": total,
        "correct": correct,
    })
