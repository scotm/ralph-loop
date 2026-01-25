"""Tests for tasks.py."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from ralph_loop.tasks import Task, TasksFile


def test_task_model():
    """Test Task model validation."""
    task = Task(
        category="test",
        description="Test task",
        steps=["Step 1", "Step 2"],
        passes=False,
    )
    assert task.category == "test"
    assert task.passes is False


def test_tasks_file_read(tmp_path: Path):
    """Test reading tasks from JSON file."""
    tasks_file = tmp_path / "tasks_list.json"
    tasks_data = [
        {
            "category": "test",
            "description": "Test task 1",
            "steps": ["Step 1"],
            "passes": False,
        },
        {
            "category": "test",
            "description": "Test task 2",
            "steps": ["Step 2"],
            "passes": True,
        },
    ]
    tasks_file.write_text(json.dumps(tasks_data))

    tf = TasksFile(tasks_file)
    tasks = tf.read_tasks()

    assert len(tasks) == 2
    assert tasks[0].passes is False
    assert tasks[1].passes is True


def test_tasks_file_not_found():
    """Test error when tasks file doesn't exist."""
    tf = TasksFile(Path("/nonexistent/tasks.json"))
    with pytest.raises(FileNotFoundError):
        tf.read_tasks()


def test_tasks_file_invalid_json(tmp_path: Path):
    """Test error when JSON is invalid."""
    tasks_file = tmp_path / "tasks_list.json"
    tasks_file.write_text("not json")

    tf = TasksFile(tasks_file)
    with pytest.raises(json.JSONDecodeError):
        tf.read_tasks()


def test_tasks_file_not_list(tmp_path: Path):
    """Test error when JSON is not a list."""
    tasks_file = tmp_path / "tasks_list.json"
    tasks_file.write_text(json.dumps({"not": "a list"}))

    tf = TasksFile(tasks_file)
    with pytest.raises(ValueError, match="Expected tasks_list.json to contain a list"):
        tf.read_tasks()


def test_tasks_file_invalid_task(tmp_path: Path):
    """Test error when task is invalid."""
    tasks_file = tmp_path / "tasks_list.json"
    tasks_file.write_text(json.dumps([{"invalid": "task"}]))

    tf = TasksFile(tasks_file)
    with pytest.raises(ValueError, match="Invalid task"):
        tf.read_tasks()


def test_count_incomplete(tmp_path: Path):
    """Test counting incomplete tasks."""
    tasks_file = tmp_path / "tasks_list.json"
    tasks_data = [
        {"category": "test", "description": "Task 1", "steps": [], "passes": False},
        {"category": "test", "description": "Task 2", "steps": [], "passes": True},
        {"category": "test", "description": "Task 3", "steps": [], "passes": False},
    ]
    tasks_file.write_text(json.dumps(tasks_data))

    tf = TasksFile(tasks_file)
    assert tf.count_incomplete() == 2


def test_get_incomplete_tasks(tmp_path: Path):
    """Test getting incomplete tasks."""
    tasks_file = tmp_path / "tasks_list.json"
    tasks_data = [
        {"category": "test", "description": "Task 1", "steps": [], "passes": False},
        {"category": "test", "description": "Task 2", "steps": [], "passes": True},
        {"category": "test", "description": "Task 3", "steps": [], "passes": False},
    ]
    tasks_file.write_text(json.dumps(tasks_data))

    tf = TasksFile(tasks_file)
    incomplete = tf.get_incomplete_tasks()
    assert len(incomplete) == 2
    assert all(not task.passes for task in incomplete)
