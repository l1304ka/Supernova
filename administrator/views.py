from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth.decorators import user_passes_test

from school.models import Student, Teacher, SchoolClass, Subject, SubTopic, Topic, Question


def superuser_required(view):
    return user_passes_test(lambda u: u.is_superuser, login_url="/")(view)


@superuser_required
def dashboard(request):
    return render(request, "adminpanel/dashboard.html", {
        "students": Student.objects.count(),
        "teachers": Teacher.objects.count(),
        "classes": SchoolClass.objects.count(),
        "subjects": Subject.objects.count(),
        "topics": Topic.objects.count(),
        "subtopics": SubTopic.objects.count(),
        "questions": Question.objects.count(),
    })


@superuser_required
def student_list(request):
    return render(request, "adminpanel/student_list.html", {
        "students": Student.objects.all()
    })


@superuser_required
def teacher_list(request):
    return render(request, "adminpanel/teacher_list.html", {
        "teachers": Teacher.objects.all()
    })


@superuser_required
def class_list(request):
    return render(request, "adminpanel/class_list.html", {
        "classes": SchoolClass.objects.all()
    })


# ---- добавление ----

@superuser_required
def add_student(request):
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        name = request.POST["name"]
        surname = request.POST["surname"]

        user = User.objects.create_user(username=username, password=password)
        Student.objects.create(user=user, name=name, surname=surname)

        return redirect("admin_students")

    return render(request, "adminpanel/add_student.html")


@superuser_required
def add_teacher(request):
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        name = request.POST["name"]
        surname = request.POST["surname"]

        user = User.objects.create_user(username=username, password=password, is_staff=True)
        Teacher.objects.create(user=user, name=name, surname=surname)

        return redirect("admin_teachers")

    return render(request, "adminpanel/add_teacher.html")


@superuser_required
def add_class(request):
    if request.method == "POST":
        name = request.POST["name"]
        school_class = SchoolClass.objects.create(name=name)
        return redirect("admin_classes")

    return render(request, "adminpanel/add_class.html")


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
    all_topics = Topic.objects.all()

    if request.method == "POST":
        subject.name = request.POST["name"]

        # обновляем список тем
        selected_topics = request.POST.getlist("topics")
        subject.topics.set(selected_topics)

        subject.save()
        return redirect("admin_subjects")

    return render(request, "adminpanel/edit_subject.html", {
        "section": "subjects",
        "subject": subject,
        "all_topics": all_topics
    })



@superuser_required
def delete_subject(request, id):
    subject = get_object_or_404(Subject, id=id)
    subject.delete()
    return redirect("admin_subjects")

# ---------- TOPICS ----------
@superuser_required
def topic_list(request):
    return render(request, "adminpanel/topic_list.html", {
        "section": "topics",
        "topics": Topic.objects.all()
    })


@superuser_required
def add_topic(request):
    if request.method == "POST":
        name = request.POST["name"]
        Topic.objects.create(name=name)
        return redirect("admin_topics")

    return render(request, "adminpanel/add_topic.html", {
        "section": "topics"
    })


@superuser_required
def edit_topic(request, id):
    topic = get_object_or_404(Topic, id=id)
    all_subtopics = SubTopic.objects.all()

    if request.method == "POST":
        topic.name = request.POST["name"]

        selected_subtopics = request.POST.getlist("subtopics")
        topic.subtopics.set(selected_subtopics)

        topic.save()
        return redirect("admin_topics")

    return render(request, "adminpanel/edit_topic.html", {
        "section": "topics",
        "topic": topic,
        "all_subtopics": all_subtopics
    })


@superuser_required
def delete_topic(request, id):
    topic = get_object_or_404(Topic, id=id)
    topic.delete()
    return redirect("admin_topics")


# ---------- SUBTOPICS ----------
@superuser_required
def subtopic_list(request):
    return render(request, "adminpanel/subtopic_list.html", {
        "section": "subtopics",
        "subtopics": SubTopic.objects.all()
    })


@superuser_required
def add_subtopic(request):
    if request.method == "POST":
        name = request.POST["name"]
        SubTopic.objects.create(name=name)
        return redirect("admin_subtopics")

    return render(request, "adminpanel/add_subtopic.html", {
        "section": "subtopics"
    })


@superuser_required
def edit_subtopic(request, id):
    subtopic = get_object_or_404(SubTopic, id=id)

    if request.method == "POST":
        subtopic.name = request.POST["name"]
        subtopic.save()
        return redirect("admin_subtopics")

    return render(request, "adminpanel/edit_subtopic.html", {
        "section": "subtopics",
        "subtopic": subtopic
    })


@superuser_required
def delete_subtopic(request, id):
    subtopic = get_object_or_404(SubTopic, id=id)
    subtopic.delete()
    return redirect("admin_subtopics")


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


# ---------- QUESTIONS ----------
@superuser_required
def question_list(request):
    questions = Question.objects.select_related("subtopic").all()
    return render(request, "adminpanel/question_list.html", {
        "section": "questions",
        "questions": questions,
    })


@superuser_required
def add_question(request):
    subtopics = SubTopic.objects.all()

    if request.method == "POST":
        subtopic_id = request.POST["subtopic"]
        text = request.POST["text"]
        difficulty = request.POST["difficulty"]
        is_open = request.POST.get("is_open") == "on"
        correct_answer = request.POST["correct_answer"]

        Question.objects.create(
            subtopic_id=subtopic_id,
            text=text,
            difficulty=difficulty,
            is_open=is_open,
            correct_answer=correct_answer,
        )
        return redirect("admin_questions")

    return render(request, "adminpanel/add_question.html", {
        "section": "questions",
        "subtopics": subtopics,
    })


@superuser_required
def edit_question(request, id):
    question = get_object_or_404(Question, id=id)
    subtopics = SubTopic.objects.all()

    if request.method == "POST":
        question.subtopic_id = request.POST["subtopic"]
        question.text = request.POST["text"]
        question.difficulty = request.POST["difficulty"]
        question.is_open = request.POST.get("is_open") == "on"
        question.correct_answer = request.POST["correct_answer"]
        question.save()
        return redirect("admin_questions")

    return render(request, "adminpanel/edit_question.html", {
        "section": "questions",
        "question": question,
        "subtopics": subtopics,
    })


@superuser_required
def delete_question(request, id):
    question = get_object_or_404(Question, id=id)
    question.delete()
    return redirect("admin_questions")
