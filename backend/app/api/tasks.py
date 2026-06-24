"""Task-list API routes for the v0.3 local application."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.core.tasks.task_service import (
    ALLOWED_TASK_STATUSES,
    TaskNotFoundError,
    list_active_tasks,
    set_task_status,
)


router = APIRouter(prefix="/api/local/tasks", tags=["local-tasks"])


class TaskStatusUpdate(BaseModel):
    status: str


@router.get("")
def get_active_tasks() -> dict[str, object]:
    return list_active_tasks()


@router.patch("/{task_id}/status")
def update_task_status(task_id: str, body: TaskStatusUpdate) -> dict[str, str]:
    if body.status not in ALLOWED_TASK_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid task status")

    try:
        set_task_status(task_id, body.status)
    except TaskNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return {"task_id": task_id, "status": body.status}
