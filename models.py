class Task:
    def init(self, title, priority, is_done=False, task_id=None):
        self.title = title
        self.priority = priority
        self.is_done = is_done
        self.id = task_id

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'priority': self.priority,
            'isDone': self.is_done
        }