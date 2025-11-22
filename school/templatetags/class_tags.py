from django import template

register = template.Library()

@register.filter
def class_list(student):
    """
    Возвращает список классов ученика как строку: '8А, 8Б'
    """
    classes = student.classes.all()
    if not classes:
        return "—"
    return ", ".join(cls.name for cls in classes)
