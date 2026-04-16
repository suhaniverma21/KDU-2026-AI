def student_task(description: str = ""):
    """
    Marker decorator or wrapper to indicate a task meant for students.
    It attaches a hint but does not alter behavior.
    """
    def decorator(obj):
        obj.__student_task__ = description
        return obj

    return decorator

