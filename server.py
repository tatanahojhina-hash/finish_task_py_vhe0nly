from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse, parse_qs


TASKS_FILENAME = 'tasks.txt'
ALLOWED_PRIORITIES = {"low", "normal", "high"}


def log(message: str) -> None:

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


@dataclass
class Task:

    title: str
    priority: str
    isDone: bool
    id: int

class TaskStorage:

    def __init__(self, filename: str):

        self._filename = filename
        self._tasks_by_id: dict[int, Task] = {}
        self._next_task_id = 1
        self._load_from_file()

    def list_tasks(self, *, is_done: Optional[bool] = None, priority: Optional[str] = None) -> list[Task]:

        tasks = list(self._tasks_by_id.values())
        tasks.sort(key=lambda t: t.id)

        if is_done is not None:
            tasks = [t for t in tasks if t.isDone == is_done]

        if priority is not None:
            tasks = [t for t in tasks if t.priority == priority]

        return tasks

    def create_task(self, title: str, priority: str) -> Task:

        task = Task(title=title, priority=priority, isDone=False, id=self._next_task_id)
        self._tasks_by_id[task.id] = task
        self._next_task_id += 1
        self._save_to_file_atomic()
        return task

    def mark_task_completed(self, task_id: int) -> bool:

        task = self._tasks_by_id.get(task_id)
        if task is None:
            return False
        task.isDone = True
        self._save_to_file_atomic()
        return True

    def _load_from_file(self) -> None:
       
        if not os.path.exists(self._filename):
            return

        with open(self._filename, "r", encoding="utf-8") as f:
            contents = f.read().strip()
            if not contents:
                return

        try:
            parsed = json.loads(contents)
        except json.JSONDecodeError:
            return

        if not isinstance(parsed, list):
            return

        loaded: dict[int, Task] = {}
        max_id = 0

        for item in parsed:
            if not isinstance(item, dict):
                continue

            title = item.get("title")
            priority = item.get("priority")
            is_done = item.get("isDone")
            task_id = item.get("id")

            if (
                isinstance(title, str)
                and isinstance(priority, str)
                and priority in ALLOWED_PRIORITIES
                and isinstance(is_done, bool)
                and isinstance(task_id, int)
                and task_id > 0
            ):
                loaded[task_id] = Task(title=title, priority=priority, isDone=is_done, id=task_id)
                max_id = max(max_id, task_id)

        self._tasks_by_id = loaded
        self._next_task_id = max_id + 1

    def _save_to_file_atomic(self) -> None:
        
        data = [asdict(t) for t in self.list_tasks()]
        tmp_name = f"{self._filename}.tmp"

        with open(tmp_name, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        os.replace(tmp_name, self._filename)


storage = TaskStorage(TASKS_FILENAME)


class TaskApiHandler(BaseHTTPRequestHandler):

    def log_message(self, format: str, *args) -> None:

        log(f'{self.client_address[0]} "{self.requestline}" {args[1]}')

    def _send_json(self, status_code: int, payload: Any, extra_headers: Optional[dict[str, str]] = None) -> None:

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, status_code: int, extra_headers: Optional[dict[str, str]] = None) -> None:

        self.send_response(status_code)
        self.send_header("Content-Length", "0")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()

    def _read_request_json(self) -> Optional[Any]:

        content_length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(content_length) if content_length > 0 else b""
        if not body:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _require_json_content_type(self) -> bool:

        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        return content_type == "application/json"

    def _parse_non_negative_int(self, query: dict[str, list[str]], name: str) -> Optional[int]:

        if name not in query or not query[name]:
            return None
        value_str = query[name][0].strip()
        if not value_str.isdigit():
            return -1
        return int(value_str)

    def do_GET(self) -> None:

        parsed_url = urlparse(self.path)

        if parsed_url.path != "/tasks":
            self._send_empty(404)
            return

        query = parse_qs(parsed_url.query)

        is_done: Optional[bool] = None
        if "isDone" in query and query["isDone"]:
            value = query["isDone"][0].strip().lower()
            if value in {"true", "false"}:
                is_done = (value == "true")
            else:
                self._send_json(400, {"error": "Query 'isDone' must be 'true' or 'false'"})
                return

        priority: Optional[str] = None
        if "priority" in query and query["priority"]:
            value = query["priority"][0].strip()
            if value in ALLOWED_PRIORITIES:
                priority = value
            else:
                self._send_json(400, {"error": "Query 'priority' must be one of: low, normal, high"})
                return

        limit = self._parse_non_negative_int(query, "limit")
        offset = self._parse_non_negative_int(query, "offset")

        if limit == -1:
            self._send_json(400, {"error": "Query 'limit' must be a non-negative integer"})
            return
        if offset == -1:
            self._send_json(400, {"error": "Query 'offset' must be a non-negative integer"})
            return

        tasks = storage.list_tasks(is_done=is_done, priority=priority)

        start = offset or 0
        if start > len(tasks):
            tasks_page = []
        else:
            tasks_page = tasks[start:]

        if limit is not None:
            tasks_page = tasks_page[:limit]

        tasks_json = [asdict(t) for t in tasks_page]
        self._send_json(200, tasks_json)

    def do_POST(self) -> None:

        parsed_url = urlparse(self.path)

        if parsed_url.path == "/tasks":
            if not self._require_json_content_type():
                self._send_json(415, {"error": "Content-Type must be application/json"})
                return

            request_json = self._read_request_json()
            if not isinstance(request_json, dict):
                self._send_json(400, {"error": "Invalid JSON"})
                return

            title = request_json.get("title")
            priority = request_json.get("priority")

            if not isinstance(title, str) or not title.strip():
                self._send_json(400, {"error": "Field 'title' must be a non-empty string"})
                return

            if not isinstance(priority, str) or priority not in ALLOWED_PRIORITIES:
                self._send_json(400, {"error": "Field 'priority' must be one of: low, normal, high"})
                return

            created = storage.create_task(title.strip(), priority)
            self._send_json(201, asdict(created), extra_headers={"Location": f"/tasks/{created.id}"})
            return

        complete_match = re.fullmatch(r"/tasks/(\d+)/complete", parsed_url.path)
        if complete_match:
            task_id = int(complete_match.group(1))
            ok = storage.mark_task_completed(task_id)
            self._send_empty(200 if ok else 404)
            return

        self._send_empty(404)


def run_server(host: str = "", port: int = 8000) -> None:

    httpd = HTTPServer((host, port), TaskApiHandler)
    log(f"Server started on http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()


if __name__ == "__main__":
    run_server()