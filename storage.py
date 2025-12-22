import json
import os

from models import Task


def load_tasks():
    if os.path.exists('tasks.txt'):
        try:
            with open('tasks.txt', 'r') as f:
                content = f.read().strip()
                if not content:
                    return []
                data = json.loads(content)
                return [Task(**item) for item in data]
        except json.JSONDecodeError:
            return []
    return []


def save_tasks(tasks_list):
    with open('tasks.txt', 'w') as f:
        json.dump([task.to_dict() for task in tasks_list], f)
