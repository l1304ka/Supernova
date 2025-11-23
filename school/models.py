from django.db import models
from django.contrib.auth.models import User


class Subject(models.Model):
    name = models.CharField(max_length=100)
    topics = models.ManyToManyField('Topic', blank=True, related_name="subjects")

    def __str__(self):
        return self.name


class Lesson(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="lessons")
    topics = models.ManyToManyField('Topic', blank=True, related_name="lessons")
    title = models.CharField(max_length=100)
    date = models.DateField()

    def __str__(self):
        return f"{self.subject.name} — {self.title}"


class Topic(models.Model):
    name = models.CharField(max_length=100)
    subtopics = models.ManyToManyField('SubTopic', blank=True, related_name="topics")

    def __str__(self):
        return f"{self.name}"


class SubTopic(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name}"


class Teacher(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    surname = models.CharField(max_length=100)
    patronymic = models.CharField(max_length=100, blank=True)
    subjects = models.ManyToManyField(Subject, related_name="teachers")

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class SchoolClass(models.Model):
    name = models.CharField(max_length=20)
    teachers = models.ManyToManyField(Teacher, related_name="classes")  # 🔹 связь "многие ко многим"4
    students = models.ManyToManyField('Student', related_name="classes")  # 🔹 связь "многие ко многим"

    def __str__(self):
        return self.name


class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    surname = models.CharField(max_length=100)
    patronymic = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Question(models.Model):
    DIFFICULTY_CHOICES = [
        ('very_easy', 'Очень легко'),
        ('easy', 'Легко'),
        ('medium', 'Средне'),
        ('hard', 'Сложно'),
        ('very_hard', 'Очень сложно'),
    ]

    subtopic = models.ForeignKey(SubTopic, on_delete=models.CASCADE, related_name="questions", null=True)

    text = models.TextField()

    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES)

    # True = открытый ответ, False = варианты
    is_open = models.BooleanField(default=False)

    # Варианты ответа (могут быть пустыми, если is_open=True)
    option_1 = models.CharField(max_length=255, blank=True)
    option_2 = models.CharField(max_length=255, blank=True)
    option_3 = models.CharField(max_length=255, blank=True)
    option_4 = models.CharField(max_length=255, blank=True)

    # Правильный вариант (1–4 или текст для открытого)
    correct_answer = models.CharField(max_length=255)

    def get_correct_text(self):
        """Человекочитаемый текст правильного ответа."""
        if self.is_open:
            return self.correct_answer

        mapping = {
            "1": self.option_1,
            "2": self.option_2,
            "3": self.option_3,
            "4": self.option_4,
        }
        return mapping.get(self.correct_answer, self.correct_answer)

    def __str__(self):
        return f"{self.subtopic}: {self.text[:30]}"


class Test(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="tests")
    assigned_topic = models.ForeignKey('AssignedTopic', on_delete=models.SET_NULL, null=True, blank=True)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=150)
    date_available = models.DateField()
    questions = models.ManyToManyField(Question, blank=True)
    maximin_questions = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.assigned_topic}: {self.lesson.subject.name} — {self.title}"


class TestResult(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    test = models.ForeignKey(Test, on_delete=models.CASCADE)
    assigned_topic = models.ForeignKey('AssignedTopic', on_delete=models.SET_NULL, null=True, blank=True)
    score = models.IntegerField()
    grade = models.IntegerField()
    completed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student} — {self.test} ({self.grade})"


class AssignedTopic(models.Model):
    """Назначенная тема для класса (домашка / адаптивный тест)"""
    title = models.CharField(max_length=150, blank=True)
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name="assigned_topics")
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="assigned_to_classes")
    assigned_by = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="given_topics")
    date_assigned = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    question_count = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.title}: {self.topic.name} → {self.school_class.name}"


class StudentAnswer(models.Model):
    result = models.ForeignKey("TestResult", on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey("Question", on_delete=models.SET_NULL, null=True)
    given_answer = models.CharField(max_length=255)
    is_correct = models.BooleanField()

    def get_given_text(self):
        """Человекочитаемый текст ответа ученика."""
        if not self.question:
            return self.given_answer

        if self.question.is_open:
            return self.given_answer

        mapping = {
            "1": self.question.option_1,
            "2": self.question.option_2,
            "3": self.question.option_3,
            "4": self.question.option_4,
        }
        return mapping.get(self.given_answer, self.given_answer)

    def __str__(self):
        return f"{self.result.student} → {self.question} ({'✔' if self.is_correct else '✘'})"
