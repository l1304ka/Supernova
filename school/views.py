import json
import random

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Avg, FloatField
from django.db.models.functions import Cast
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.timezone import now

from administrator.views import superuser_required
from .ai_utils import generate_homework_tasks_gemini
from .models import Test, TestResult, Student, Lesson, Subject, AssignedTopic, Question, StudentAnswer, Teacher, \
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
        students = Student.objects.filter(classes__in=classes).distinct()

        # --- Статистика тестов ---
        stats = []
        for s in students:
            results = TestResult.objects.filter(student=s).order_by("-completed_at")
            avg_grade = round(sum(r.grade for r in results) / len(results), 2) if results else None

            stats.append({
                "student": s,
                "results": results,
                "avg_grade": avg_grade,
            })

        # --- Статистика ДЗ ---
        homeworks = Homework.objects.filter(student__in=students).prefetch_related("tasks")

        hw_total = homeworks.count()
        hw_checked = homeworks.filter(is_checked=True).count()
        hw_in_progress = homeworks.filter(is_checked=False).count()

        hw_percent_avg = HomeworkTask.objects.filter(
            homework__student__in=students,
            is_correct__isnull=False
        ).aggregate(avg=Avg("is_correct"))["avg"] or 0

        hw_percent_avg = round(hw_percent_avg * 100)

        # по ученикам
        hw_per_student = []
        for s in students:
            s_homeworks = Homework.objects.filter(student=s).prefetch_related("tasks")

            total = s_homeworks.count()
            done = s_homeworks.filter(is_checked=True).count()

            tasks_total = HomeworkTask.objects.filter(homework__student=s, is_correct__isnull=False)
            percent = 0
            if tasks_total.exists():
                percent = round(
                    tasks_total.filter(is_correct=True).count() * 100 / tasks_total.count()
                )

            hw_per_student.append({
                "student": s,
                "total": total,
                "done": done,
                "percent": percent,
            })

        # ─────────────────────────────────────
        # ЕДИНЫЙ СПИСОК СОБЫТИЙ (до 300 последних)
        # ─────────────────────────────────────
        event_list = []

        # TEST RESULTS
        test_results = TestResult.objects.filter(student__in=students).order_by("-completed_at")[:150]
        for r in test_results:
            event_list.append({
                "type": "test",
                "student": f"{r.student.name} {r.student.surname}",
                "title": r.assigned_topic.title,
                "grade": r.grade,
                "date": r.completed_at,
            })

        # HOMEWORK CREATED
        hw_created = Homework.objects.filter(student__in=students).order_by("-created_at")[:100]
        for hw in hw_created:
            event_list.append({
                "type": "hw_created",
                "student": f"{hw.student.name} {hw.student.surname}",
                "title": hw.lesson.title,
                "date": hw.created_at,
            })

        # HOMEWORK CHECKED
        hw_checked_list = Homework.objects.filter(student__in=students, is_checked=True).order_by("-created_at")[:100]
        for hw in hw_checked_list:
            tasks = hw.tasks.all()
            correct = tasks.filter(is_correct=True).count()
            total = tasks.count()
            percent = int(correct * 100 / total) if total else 0

            event_list.append({
                "type": "hw_checked",
                "student": f"{hw.student.name} {hw.student.surname}",
                "title": hw.lesson.title,
                "score": f"{correct}/{total}",
                "percent": percent,
                "date": hw.created_at,
            })

        # Сортировка по дате и берём только 100
        event_list = sorted(event_list, key=lambda x: x["date"], reverse=True)[:100]

        # JSON для JS (пагинация, фильтрация)
        recent_events_json = json.dumps([
            {
                "type": e["type"],
                "student": e["student"],
                "title": e["title"],
                "grade": e.get("grade"),
                "score": e.get("score"),
                "percent": e.get("percent"),
                "date": e["date"].isoformat(),
            }
            for e in event_list
        ], cls=DjangoJSONEncoder)

        # ===== ТЕСТЫ: ГЛОБАЛЬНАЯ СТАТИСТИКА =====
        assigned = AssignedTopic.objects.filter(school_class__in=classes)
        total_tests_assigned = assigned.count()

        done_tests = TestResult.objects.filter(student__in=students).count()

        if total_tests_assigned > 0:
            test_completion_percent = round(done_tests * 100 / total_tests_assigned)
        else:
            test_completion_percent = 0

        # средняя оценка
        avg_test_grade = TestResult.objects.filter(student__in=students).aggregate(
            g=Avg("grade")
        )["g"]
        if avg_test_grade:
            avg_test_grade = round(avg_test_grade, 2)
        else:
            avg_test_grade = 0

        # средний процент score по тестам
        avg_test_score = TestResult.objects.filter(student__in=students).aggregate(
            s=Avg("score")
        )["s"]
        if avg_test_score:
            avg_test_score = round(avg_test_score)
        else:
            avg_test_score = 0

        return render(request, "teacher_dashboard.html", {
            "teacher": teacher,
            "classes": classes,
            "stats": stats,

            "hw_total": hw_total,
            "hw_checked": hw_checked,
            "hw_in_progress": hw_in_progress,
            "hw_percent_avg": hw_percent_avg,
            "hw_per_student": hw_per_student,

            "test_completion_percent": test_completion_percent,
            "avg_test_grade": avg_test_grade,
            "avg_test_score": avg_test_score,

            "recent_events_json": recent_events_json,
        })

    # ─────────────────────────────────────────────
    # БЛОК ДЛЯ УЧЕНИКА
    # ─────────────────────────────────────────────
    elif hasattr(user, 'student'):
        from django.utils import timezone
        now = timezone.now()

        student = user.student
        classes = student.classes.all()

        # Все назначенные темы (с учетом дедлайна)
        assigned_topics = AssignedTopic.objects.filter(
            school_class__in=classes,
            is_active=True
        ).filter(
            models.Q(deadline__isnull=True) | models.Q(deadline__gt=now)
        ).distinct()

        # Завершённые тесты
        results_all = TestResult.objects.filter(
            student=student
        ).select_related("assigned_topic").order_by("-completed_at")

        finished_ids = set(results_all.values_list("assigned_topic_id", flat=True))

        # Берем только последние 5
        results = results_all[:5]
        last_result = results_all.first() if results_all else None

        # Незавершённые тесты
        adaptive_tests = request.session.get("adaptive_tests", {})

        unfinished_tests = []
        for assigned_id_str in adaptive_tests.keys():
            try:
                assigned = AssignedTopic.objects.get(id=int(assigned_id_str))
                if assigned.deadline is None or assigned.deadline > now:
                    unfinished_tests.append(assigned)
            except AssignedTopic.DoesNotExist:
                pass

        unfinished_ids = {u.id for u in unfinished_tests}

        # Доступные тесты: не завершённые, не незавершённые и дедлайн не прошёл
        available_tests = assigned_topics.exclude(
            id__in=finished_ids | unfinished_ids
        )
        for t in available_tests:
            print(t.deadline)

        # ─────────────────────────────────────────────
        # ДОМАШНИЕ ЗАДАНИЯ (с дедлайном!)
        # ─────────────────────────────────────────────
        all_homeworks = Homework.objects.filter(student=student).prefetch_related("tasks")

        homework_in_progress = []
        homework_done = []
        hw_waiting = []

        # ДЗ, которые должны быть сгенерированы:
        for r in results_all:
            if not hasattr(r, "homework") or r.homework is None:
                # Проверяем дедлайн самого AssignedTopic
                assigned_topic = r.assigned_topic
                if assigned_topic.deadline is None or assigned_topic.deadline > now:
                    hw_waiting.append(r)

        # Обрабатываем ДЗ
        for hw in all_homeworks:

            # Пропускаем ДЗ, у которых прошёл дедлайн и они не проверены
            if hw.deadline and hw.deadline < now and not hw.is_checked:
                continue

            tasks = list(hw.tasks.all())
            total = len(tasks)
            solved_raw = len([t for t in tasks if t.is_correct is not False])  # used earlier
            percent = int((solved_raw / total) * 100) if total else 0

            item = {
                "hw": hw,
                "lesson": hw.lesson,
                "total": total,
                "solved": solved_raw,
                "percent": percent,
                "deadline": hw.deadline
            }

            if hw.is_checked:
                homework_done.append(item)
            else:
                # показываем количество реально решённых
                item["solved"] = len([t for t in tasks if t.is_correct is not None])
                homework_in_progress.append(item)

        # === TESTS ===
        tests_total = assigned_topics.count()
        tests_done = results.count()

        avg_score = round(results.aggregate(Avg("score"))["score__avg"] or 0)
        avg_grade = round(results.aggregate(Avg("grade"))["grade__avg"] or 0, 1)

        # === HOMEWORK ===
        hw_total = all_homeworks.count()
        hw_done = all_homeworks.filter(is_checked=True).count()

        hw_avg_percent = HomeworkTask.objects.filter(
            homework__student=student,
            is_correct__isnull=False
        ).aggregate(avg=Avg(Cast("is_correct", FloatField())))["avg"]

        hw_avg_percent = int(hw_avg_percent * 100) if hw_avg_percent else 0

        hw_overdue = all_homeworks.filter(
            deadline__lt=timezone.now(),
            is_checked=False
        ).count()

        # === PER SUBJECT STATS ===
        subject_stats = []
        subjects = student.classes.values_list("subjects__name", flat=True).distinct()

        for name in subjects:
            subj_results = TestResult.objects.filter(
                student=student,
                test__lesson__subject__name=name
            )

            if subj_results.exists():
                p = int(subj_results.aggregate(avg=Avg("score"))["avg"])
            else:
                p = 0

            subject_stats.append({
                "name": name,
                "percent": p,
            })

        # История тестов (баллы)
        tests_history = list(
            TestResult.objects.filter(student=student)
            .order_by("completed_at")
            .values_list("score", flat=True)
        )

        # История ДЗ (в процентах)
        hw_history = []
        for hw in Homework.objects.filter(student=student).order_by("created_at"):
            correct = hw.tasks.filter(is_correct=True).count()
            total = hw.tasks.count()
            percent = int(correct * 100 / total) if total else 0
            hw_history.append(percent)

        return render(request, "index.html", {
            "results": results,
            "unfinished_tests": unfinished_tests,
            "available_tests": available_tests,
            "last_result": last_result,

            "homework_list": homework_in_progress,  # 🟡 В процессе
            "homework_done": homework_done,  # 🟢 Выполненные
            "hw_waiting": hw_waiting,  # 🟠 Ждущие генерации

            "tests_total": tests_total,
            "tests_done": tests_done,
            "avg_score": avg_score,
            "avg_grade": avg_grade,

            "hw_total": hw_total,
            "hw_done": hw_done,
            "hw_avg_percent": hw_avg_percent,
            "hw_overdue": hw_overdue,

            "subject_stats": subject_stats,
            "tests_history": tests_history,
            "hw_history": hw_history,

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
def get_lessons_by_subject(request):
    """Возвращает уроки по выбранному предмету"""
    subject_id = request.GET.get("subject_id")
    if not subject_id:
        return JsonResponse({"error": "no subject_id"}, status=400)

    print(subject_id)
    try:
        subject = Subject.objects.get(id=subject_id)
    except Subject.DoesNotExist:
        return JsonResponse({"error": "subject not found"}, status=404)

    lessons = subject.lessons.all().values("id", "title")
    print(len(lessons))
    return JsonResponse({"lessons": list(lessons)})


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
            subtopic__topics__lessons=assigned.lesson,
            difficulty="medium"
        )
        if not qs.exists():
            qs = Question.objects.filter(subtopic__topics__lessons=assigned.lesson,)

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

        final_test = Test.objects.create(
            lesson=assigned.lesson,
            title=assigned.lesson.title,
            date_available=now().date(),
            assigned_topic=assigned,
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
        subtopic__topics__lessons=assigned.lesson,
        difficulty=data["difficulty"]
    ).exclude(id__in=data["asked"])

    if not next_qs.exists():
        next_qs = Question.objects.filter(
            subtopic__topics__lessons=assigned.lesson,
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

    homeworks = Homework.objects.filter(student=student)

    hw_total = homeworks.count()
    hw_checked = homeworks.filter(is_checked=True).count()
    hw_in_progress = homeworks.filter(is_checked=False).count()

    # средний процент выполненных задач
    tasks = HomeworkTask.objects.filter(homework__student=student, is_correct__isnull=False)
    if tasks.exists():
        hw_percent = round(tasks.filter(is_correct=True).count() * 100 / tasks.count())
    else:
        hw_percent = 0

    homeworks = Homework.objects.filter(student=student).order_by("-created_at")

    hw_list = []
    for hw in homeworks:
        tasks = hw.tasks.all()
        total = tasks.count()
        solved = tasks.filter(is_correct=True).count()
        percent = round(solved * 100 / total) if total else 0

        hw_list.append({
            "hw": hw,
            "total": total,
            "solved": solved,
            "percent": percent,
        })

    return render(request, "student_results.html", {
        "results": results,
        "hw_total": hw_total,
        "hw_checked": hw_checked,
        "hw_in_progress": hw_in_progress,
        "hw_percent": hw_percent,
        "hw_list": hw_list,
    })


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
        lesson_id = request.POST.get("lesson_id")
        title = request.POST.get("title", "")
        question_count = int(request.POST.get("question_count", "0"))
        deadline_str = request.POST.get("deadline")
        deadline = None

        if deadline_str:
            from django.utils.dateparse import parse_datetime
            deadline = parse_datetime(deadline_str)

        AssignedTopic.objects.create(
            title=title,
            school_class=school_class,
            lesson_id=lesson_id,
            assigned_by=teacher,
            question_count=question_count,
            deadline=deadline
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

    homeworks = Homework.objects.filter(student=student)

    hw_total = homeworks.count()
    hw_checked = homeworks.filter(is_checked=True).count()
    hw_in_progress = homeworks.filter(is_checked=False).count()

    tasks = HomeworkTask.objects.filter(homework__student=student, is_correct__isnull=False)
    if tasks.exists():
        hw_percent = round(tasks.filter(is_correct=True).count() * 100 / tasks.count())
    else:
        hw_percent = 0

    homeworks = Homework.objects.filter(student=student).order_by("-created_at")

    hw_list = []
    for hw in homeworks:
        tasks = hw.tasks.all()
        total = tasks.count()
        solved = tasks.filter(is_correct=True).count()
        percent = round(solved * 100 / total) if total else 0

        hw_list.append({
            "hw": hw,
            "total": total,
            "solved": solved,
            "percent": percent,
        })

    return render(request, "teacher_student_detail.html", {
        "student": student,
        "results": results,
        "hw_total": hw_total,
        "hw_checked": hw_checked,
        "hw_in_progress": hw_in_progress,
        "hw_percent": hw_percent,
        "hw_list": hw_list,
    })


@login_required
def class_tests(request, class_id):
    school_class = get_object_or_404(SchoolClass, id=class_id)

    # назначенные темы
    assigned = AssignedTopic.objects.filter(school_class=school_class)
    assigned = assigned.order_by("-date_assigned")

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

    tests = dict(sorted(tests.items(), key=lambda item: item[1]["test"].date_available, reverse=True))

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
    """Создать ИИ-домашку по результату теста — с защитой от повторных кликов."""
    result = get_object_or_404(TestResult, id=result_id, student__user=request.user)

    # если ДЗ уже создано
    if hasattr(result, "homework"):
        return redirect("homework_detail", homework_id=result.homework.id)

    # если ДЗ уже в процессе генерации
    if result.is_homework_generating:
        return redirect("index")

    # помечаем что генерация началась
    result.is_homework_generating = True
    result.save()

    try:
        assigned = result.assigned_topic
        student = result.student

        tasks_count = 3

        if result.score >= 85:
            diff_hint = "чуть выше среднего уровня, можно включить 1–2 сложные задачи"
        elif result.score >= 60:
            diff_hint = "средний уровень"
        else:
            diff_hint = "чуть проще среднего уровня, чтобы закрепить базу"

        topics_name = assigned.lesson.topics.all().values_list("name", flat=True)
        topics_name = ", ".join(topics_name)

        tasks_data = generate_homework_tasks_gemini(
            topics_name=topics_name,
            tasks_count=tasks_count,
            difficulty_hint=diff_hint,
            score_percent=result.score,
        )

        hw = Homework.objects.create(
            student=student,
            test_result=result,
            lesson=assigned.lesson,
            tasks_count=len(tasks_data),
            deadline=assigned.deadline,
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

    finally:
        # снимаем блокировку в любом случае
        result.is_homework_generating = False
        result.save()


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

    # расчёт прогресса
    solved = len([t for t in tasks if t.is_correct is not False])
    percent = int((solved / total) * 100) if total else 0

    return render(request, "homework_detail.html", {
        "homework": hw,
        "tasks": tasks,
        "total": total,
        "correct": correct,
        "solved": solved,
        "percent": percent,
    })


@login_required
def homework_result(request, homework_id):
    hw = get_object_or_404(Homework, id=homework_id, student__user=request.user)
    tasks = list(hw.tasks.order_by("order"))

    total = len(tasks)
    correct = len([t for t in tasks if t.is_correct])

    return render(request, "homework_result.html", {
        "homework": hw,
        "tasks": tasks,
        "total": total,
        "correct": correct,
    })


@login_required
def create_lesson(request):
    user = request.user

    if not hasattr(user, "teacher"):
        return redirect("index")

    teacher = user.teacher
    subjects = teacher.subjects.all()

    if request.method == "POST":
        subject_id = request.POST.get("subject")
        title = request.POST.get("title")
        date = request.POST.get("date")
        topic_ids = request.POST.getlist("topics")

        if subject_id and title and date:
            subject = Subject.objects.get(id=subject_id)

            lesson = Lesson.objects.create(
                subject=subject,
                title=title,
                date=date
            )

            if topic_ids:
                lesson.topics.set(topic_ids)

            return redirect("index")

    return render(request, "create_lesson.html", {
        "subjects": subjects,
    })
