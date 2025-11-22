from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="admin_dashboard"),

    # управление пользователями
    path("students/", views.student_list, name="admin_students"),
    path("teachers/", views.teacher_list, name="admin_teachers"),
    path("classes/", views.class_list, name="admin_classes"),

    # добавление
    path("students/add/", views.add_student, name="admin_add_student"),
    path("teachers/add/", views.add_teacher, name="admin_add_teacher"),
    path("classes/add/", views.add_class, name="admin_add_class"),
    path("subjects/", views.subject_list, name="admin_subjects"),
    path("subjects/add/", views.add_subject, name="admin_add_subject"),
    path("subjects/<int:id>/edit/", views.edit_subject, name="admin_edit_subject"),
    path("subjects/<int:id>/delete/", views.delete_subject, name="admin_delete_subject"),

# TOPICS
path("topics/", views.topic_list, name="admin_topics"),
path("topics/add/", views.add_topic, name="admin_add_topic"),
path("topics/<int:id>/edit/", views.edit_topic, name="admin_edit_topic"),
path("topics/<int:id>/delete/", views.delete_topic, name="admin_delete_topic"),

# SUBTOPICS
path("subtopics/", views.subtopic_list, name="admin_subtopics"),
path("subtopics/add/", views.add_subtopic, name="admin_add_subtopic"),
path("subtopics/<int:id>/edit/", views.edit_subtopic, name="admin_edit_subtopic"),
path("subtopics/<int:id>/delete/", views.delete_subtopic, name="admin_delete_subtopic"),

path("classes/<int:id>/assign-teachers/", views.assign_teachers, name="admin_assign_teachers"),
path("classes/<int:id>/assign-students/", views.assign_students, name="admin_assign_students"),

# QUESTIONS
path("questions/", views.question_list, name="admin_questions"),
path("questions/add/", views.add_question, name="admin_add_question"),
path("questions/<int:id>/edit/", views.edit_question, name="admin_edit_question"),
path("questions/<int:id>/delete/", views.delete_question, name="admin_delete_question"),

]
