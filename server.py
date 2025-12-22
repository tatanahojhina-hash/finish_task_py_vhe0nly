import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from models import Task
from storage import load_tasks, save_tasks

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

tasks = load_tasks()
next_id = max([t.id for t in tasks] + [0]) + 1

class TodoHandler:
    pass



class TodoHandler(BaseHTTPRequestHandler):
    def do_GET(self):

        if self.path.startswith('/tasks'):
            parsed_path = urlparse(self.path)
            query = parse_qs(parsed_path.query)
            priority_filter = query.get('priority', [None])[0]  # Фильтр по priority (улучшение)

            filtered_tasks = tasks
            if priority_filter:
                filtered_tasks = [t for t in tasks if t.priority == priority_filter]

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps([task.to_dict() for task in filtered_tasks]).encode('utf-8'))
            logging.info(f"GET /tasks - returned {len(filtered_tasks)} tasks")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):

        global tasks, next_id
        if self.path == '/tasks':

            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                if 'title' not in data or 'priority' not in data or not data['title'].strip():
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b'{"error": "Missing or invalid title/priority"}')
                    return
                if data['priority'] not in ['low', 'normal', 'high']:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b'{"error": "Priority must be low, normal, or high"}')
                    return
                task = Task(data['title'], data['priority'], task_id=next_id)
                next_id += 1
                tasks.append(task)
                save_tasks(tasks)
                self.send_response(201)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(task.to_dict()).encode('utf-8'))
                logging.info(f"POST /tasks - created task {task.id}")
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error": "Invalid JSON"}')
        elif self.path.startswith('/tasks/') and self.path.endswith('/complete'):
            # Отметка задачи как выполненной
            try:
                task_id = int(self.path.split('/')[2])
                for task in tasks:
                    if task.id == task_id:
                        task.is_done = True
                        save_tasks(tasks)
                        self.send_response(200)
                        self.end_headers()
                        logging.info(f"POST /tasks/{task_id}/complete - marked as done")
                        return
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'{"error": "Task not found"}')
            except ValueError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error": "Invalid task ID"}')
        else:
            self.send_response(404)
            self.end_headers()

        def do_DELETE(self):
            # Обработка DELETE-запросов: удаление задачи (дополнительное улучшение)
            global tasks
            if self.path.startswith('/tasks/'):
                try:
                    task_id = int(self.path.split('/')[2])
                    for i, task in enumerate(tasks):
                        if task.id == task_id:
                            del tasks[i]
                            save_tasks(tasks)
                            self.send_response(200)
                            self.end_headers()
                            logging.info(f"DELETE /tasks/{task_id} - deleted")
                            return
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b'{"error": "Task not found"}')
                except ValueError:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b'{"error": "Invalid task ID"}')
            else:
                self.send_response(404)
                self.end_headers()


    if __name__ == '__main__':
        server_address = ('', 8000)
        httpd = HTTPServer(server_address, TodoHandler)
        logging.info('Server running on port 8000...')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logging.info('Server stopped.')
            httpd.shutdown()
