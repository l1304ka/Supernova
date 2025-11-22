import random
from urllib import request

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.timezone import now

from administrator.views import superuser_required
from .models import Test, TestResult, Student, Topic, Lesson, Subject, AssignedTopic, Question, StudentAnswer, Teacher, \
    SchoolClass


@login_required
def index(request):
    user = request.user

    # если учитель
    if hasattr(user, 'teacher'):
        teacher = user.teacher
        classes = teacher.classes.all()
        subjects = teacher.subjects.all()
        students = Student.objects.filter(classes__in=classes).distinct()

        stats = []
        for s in students:
            results = TestResult.objects.filter(student=s)
            avg_grade = round(sum(r.grade for r in results) / len(results), 2) if results else None
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

    # если ученик
    elif hasattr(user, 'student'):
        student = user.student
        classes = student.classes.all()

        # темы, назначенные классу
        assigned_tests = AssignedTopic.objects.filter(school_class__in=classes, is_active=True)

        # результаты ученика
        results = TestResult.objects.filter(student=student).order_by("-completed_at")
        last_result = results.first()

        # доступные темы (которые ещё не пройдены)
        available_tests = []
        for at in assigned_tests:
            for result in results:
                if result.assigned_topic == at:
                    break
            else:
                available_tests.append(at)

        print(assigned_tests)
        print(available_tests)

        return render(request, "index.html", {
            "available_tests": available_tests,
            "results": results,
            "last_result": last_result,
        })

    else:
        return render(request, "index.html", {"available_topics": [], "results": []})


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


@login_required
def adaptive_test(request, test_id):
    student = request.user.student
    assigned = get_object_or_404(AssignedTopic, id=test_id, is_active=True)

    # Уже проходил — редирект
    if TestResult.objects.filter(student=student, assigned_topic=assigned).exists():
        return redirect("index")

    # =========================
    #     НАЧАЛО ТЕСТА (GET)
    # =========================
    if request.method == "GET":

        # Инициализация сессии
        data = {
            "assigned_id": assigned.id,
            "step": 1,
            "difficulty": "medium",
            "correct": 0,
            "wrong": 0,
            "asked_ids": [],
            "answers": []  # чтобы хранить ВСЕ ответы
        }

        # Выбор первого вопроса
        next_q = Question.objects.filter(
            subtopic__topics=assigned.topic,
            difficulty="medium"
        )

        if not next_q.exists():
            next_q = Question.objects.filter(subtopic__topics=assigned.topic)

        question = random.choice(list(next_q))
        data["asked_ids"].append(question.id)

        request.session["adaptive"] = data

        return render(request, "adaptive_test.html", {
            "step": 1,
            "question": question,
            "difficulty": "medium"
        })

    # =========================
    #     ОБРАБОТКА POST
    # =========================
    data = request.session.get("adaptive")
    if not data:
        return redirect("index")

    qid = int(request.POST.get("question_id"))
    question = get_object_or_404(Question, id=qid)

    given_answer = request.POST.get("answer", "").strip().lower()
    correct_answer = question.correct_answer.strip().lower()

    is_correct = (given_answer == correct_answer)

    # Сохраняем ответ в сессии
    data["answers"].append({
        "question_id": question.id,
        "given_answer": given_answer,
        "correct": is_correct
    })

    # Обновляем статистику
    if is_correct:
        data["correct"] += 1
        data["difficulty"] = increase_difficulty(data["difficulty"])
    else:
        data["wrong"] += 1
        data["difficulty"] = decrease_difficulty(data["difficulty"])

    data["step"] += 1
    request.session["adaptive"] = data

    # =========================
    #      ЗАВЕРШЕНИЕ ТЕСТА
    # =========================
    if data["step"] > 10:
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
            topic=assigned.topic
        )

        result = TestResult.objects.create(
            student=student,
            test=final_test,
            assigned_topic=assigned,
            score=pct,
            grade=grade
        )

        # Сохраняем ВСЕ ответы
        for item in data["answers"]:
            q = Question.objects.get(id=item["question_id"])
            StudentAnswer.objects.create(
                result=result,
                question=q,
                given_answer=item["given_answer"],
                is_correct=item["correct"]
            )

        del request.session["adaptive"]

        return redirect("test_result_detail", result.id)

    # =========================
    #     ВЫБОР СЛЕД. ВОПРОСА
    # =========================
    next_q = Question.objects.filter(
        subtopic__topics=assigned.topic,
        difficulty=data["difficulty"]
    ).exclude(id__in=data["asked_ids"])

    # Фоллбек — любые вопросы, если по сложности нет
    if not next_q.exists():
        next_q = Question.objects.filter(
            subtopic__topics=assigned.topic
        ).exclude(id__in=data["asked_ids"])

    # Если вопросов вообще не осталось
    if not next_q.exists():
        return redirect("index")  # или показать сообщение

    question = random.choice(list(next_q))
    data["asked_ids"].append(question.id)
    request.session["adaptive"] = data

    return render(request, "adaptive_test.html", {
        "step": data["step"],
        "question": question,
        "difficulty": data["difficulty"]
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

        AssignedTopic.objects.create(
            title=title,
            school_class=school_class,
            topic_id=topic_id,
            assigned_by=teacher
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
