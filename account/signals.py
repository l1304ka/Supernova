from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from school.models import Student, Teacher


@receiver(post_save, sender=User)
def create_role_profile(sender, instance, created, **kwargs):
    """
    Автоматически создаёт Student/Teacher, если суперпользователь указал роль.
    Роль храним в User.is_staff (учитель) и User.is_superuser.
    - Учитель → is_staff=True, is_superuser=False
    - Ученик → is_staff=False
    - Админ → is_superuser=True
    """
    if not created:
        return

    if instance.is_superuser:
        return  # суперпользователь — отдельный тип, профиль не нужен

    if instance.is_staff:
        # учитель
        Teacher.objects.create(
            user=instance,
            name=instance.username,
            surname="Фамилия"
        )
    else:
        # ученик
        Student.objects.create(
            user=instance,
            name=instance.username,
            surname="Фамилия"
        )
