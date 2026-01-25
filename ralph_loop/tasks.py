"""Task file reading and parsing."""

import json
from pathlib import Path

from pydantic import BaseModel, ValidationError


class Task(BaseModel):
    """Represents a single task from tasks_list.json."""

    category: str
    description: str
    steps: list[str]
    passes: bool


class TasksFile:
    """Handles reading and parsing tasks_list.json."""

    def __init__(self, path: Path):
        """Initialize with path to tasks_list.json."""
        self.path = path

    def exists(self) -> bool:
        """Check if tasks file exists."""
        return self.path.exists()

    def read_tasks(self) -> list[Task]:
        """Read and parse tasks from JSON file."""
        if not self.exists():
            raise FileNotFoundError(f"Tasks file not found: {self.path}")

        with self.path.open() as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError(f"Expected tasks_list.json to contain a list, got {type(data).__name__}")

        tasks = []
        for i, item in enumerate(data):
            try:
                task = Task(**item)
                tasks.append(task)
            except ValidationError as e:
                raise ValueError(f"Invalid task at index {i}: {e}") from e

        return tasks

    def count_incomplete(self) -> int:
        """Count tasks where passes is False."""
        tasks = self.read_tasks()
        return sum(1 for task in tasks if not task.passes)

    def get_incomplete_tasks(self) -> list[Task]:
        """Get all tasks where passes is False."""
        tasks = self.read_tasks()
        return [task for task in tasks if not task.passes]
