from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("test/<int:test_id>/", views.test_detail, name="test_detail"),
    path("test/<int:test_id>/result/", views.test_result, name="test_result"),
    path("assign_homework/", views.assign_homework, name="assign_homework"),
    path("get_topics_by_subject/", views.get_topics_by_subject, name="get_topics_by_subject"),  # ← новый
    path("adaptive_test<int:test_id>/", views.adaptive_test, name="adaptive_test"),  # ← новый
    path("results/", views.student_results, name="student_results"),
    path("adaptive/<int:test_id>/", views.adaptive_test, name="adaptive_test"),
    path("result/<int:result_id>/", views.test_result_detail, name="test_result_detail"),
    path("subjects/", views.subject_list, name="admin_subjects"),
    path("subjects/add/", views.add_subject, name="admin_add_subject"),
    path("subjects/<int:id>/edit/", views.edit_subject, name="admin_edit_subject"),
    path("subjects/<int:id>/delete/", views.delete_subject, name="admin_delete_subject"),
    path("classes/<int:id>/assign-teachers/", views.assign_teachers, name="admin_assign_teachers"),
    path("classes/<int:id>/assign-students/", views.assign_students, name="admin_assign_students"),

]
