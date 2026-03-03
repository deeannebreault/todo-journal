#!/usr/bin/env python3
"""
TODO System - Combined API + Static Server
Serves both the FastAPI backend and static HTML UI
"""

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
import os

# Import from todo_db
import sys
sys.path.insert(0, os.path.dirname(__file__))
from todo_db import TodoDB, Priority, Status, RelationshipType

app = FastAPI(title="TODO System", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database
db = TodoDB()

# Pydantic models
class TaskCreate(BaseModel):
    title: str
    description: str = ""
    priority: int = 2
    category: str = "general"
    tags: List[str] = []
    due_date: Optional[str] = None
    parent_id: Optional[int] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    status: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    due_date: Optional[str] = None

# API Routes

@app.get("/api/last-update")
def get_last_update():
    """Get the last task or journal update time and type"""
    import os
    from datetime import datetime
    
    # Get last task update
    tasks = db.get_tasks()
    last_task_time = None
    if tasks:
        last_task = max(tasks, key=lambda t: t.get('updated_at', '') or '')
        if last_task.get('updated_at'):
            last_task_time = last_task['updated_at']
    
    # Get last journal update
    journal_path = os.path.expanduser("~/.openclaw/workspace/JOURNAL.md")
    last_journal_time = None
    if os.path.exists(journal_path):
        mtime = os.path.getmtime(journal_path)
        last_journal_time = datetime.fromtimestamp(mtime).isoformat()
    
    # Determine which was last
    if last_task_time and last_journal_time:
        task_dt = datetime.fromisoformat(last_task_time.replace('Z', '+00:00')) if isinstance(last_task_time, str) else last_task_time
        journal_dt = datetime.fromisoformat(last_journal_time.replace('Z', '+00:00')) if isinstance(last_journal_time, str) else last_journal_time
        
        if task_dt > journal_dt:
            return {
                "last_update_type": "task",
                "last_update_time": last_task_time,
                "task_count": len(tasks)
            }
        else:
            return {
                "last_update_type": "journal",
                "last_update_time": last_journal_time,
                "task_count": len(tasks)
            }
    elif last_task_time:
        return {
            "last_update_type": "task",
            "last_update_time": last_task_time,
            "task_count": len(tasks)
        }
    elif last_journal_time:
        return {
            "last_update_type": "journal",
            "last_update_time": last_journal_time,
            "task_count": 0
        }
    else:
        return {
            "last_update_type": None,
            "last_update_time": None,
            "task_count": 0
        }

@app.get("/api/next-update")
def get_next_update(interval_minutes: int = 30):
    """Get the next task or journal update time and what type it should be"""
    from datetime import datetime, timedelta
    
    # Get last update info
    last_update = get_last_update()
    last_type = last_update.get("last_update_type")
    last_time = last_update.get("last_update_time")
    
    # Calculate next time
    if last_time:
        last_dt = datetime.fromisoformat(str(last_time).replace('Z', '+00:00'))
    else:
        last_dt = datetime.now()
    
    next_time = last_dt + timedelta(minutes=interval_minutes)
    
    # Determine what type the next update should be (alternate)
    if last_type == "task":
        next_type = "journal"  # Time to explore/learn
        mode = "explore"
        description = "Focus on exploration, learning, and journaling"
    elif last_type == "journal":
        next_type = "task"  # Time to work
        mode = "work"
        description = "Focus on tasks and project work"
    else:
        # Default: start with tasks
        next_type = "task"
        mode = "work"
        description = "Focus on tasks and project work"
    
    return {
        "next_update_type": next_type,
        "next_update_time": next_time.isoformat(),
        "mode": mode,
        "description": description,
        "interval_minutes": interval_minutes,
        "last_update_type": last_type,
        "last_update_time": last_time
    }

@app.get("/api/tasks")
def get_tasks(
    status: Optional[str] = None,
    priority: Optional[int] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort: Optional[str] = "updated_at",
    show_all: bool = True
):
    """Get all tasks with optional filters and sorting. Set show_all=false to hide completed tasks."""
    status_enum = Status(status) if status else None
    priority_enum = Priority(priority) if priority else None
    
    tasks = db.get_tasks(
        status=status_enum,
        priority=priority_enum,
        category=category,
        search=search
    )
    
    # By default, hide completed tasks older than today unless show_all=true
    if not show_all:
        from datetime import datetime, timedelta
        today = datetime.now().date()
        tasks = [t for t in tasks if t.get('status') != 'done' or 
                 (t.get('updated_at') and datetime.fromisoformat(t['updated_at']).date() == today)]
    
    # Sort by priority desc, then updated_at desc
    tasks = sorted(tasks, key=lambda t: (-t.get('priority', 0), t.get('updated_at') or t.get('created_at', '')), reverse=False)
    
    return {"tasks": tasks, "count": len(tasks)}

@app.get("/api/recent-activity")
def get_recent_activity(limit: int = 3):
    """Get recently updated tasks for the activity banner"""
    tasks = db.get_tasks()
    
    # Sort by most recently updated
    sorted_tasks = sorted(tasks, key=lambda t: t.get('updated_at') or t.get('created_at', ''), reverse=True)
    
    # Get top N most recently touched tasks
    recent = sorted_tasks[:limit]
    
    return {
        "recent_tasks": recent,
        "count": len(recent),
        "last_update": recent[0].get('updated_at') if recent else None
    }

@app.post("/api/tasks")
def create_task(task: TaskCreate):
    """Create a new task"""
    due = None
    if task.due_date:
        try:
            due = datetime.fromisoformat(task.due_date)
        except:
            pass
    
    task_id = db.add_task(
        title=task.title,
        description=task.description,
        priority=Priority(task.priority),
        category=task.category,
        tags=task.tags,
        due_date=due,
        parent_id=task.parent_id
    )
    return {"id": task_id, "message": "Task created successfully"}

@app.get("/api/tasks/{task_id}")
def get_task(task_id: int):
    """Get a single task"""
    tasks = db.get_tasks()
    task = next((t for t in tasks if t['id'] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.put("/api/tasks/{task_id}")
def update_task(task_id: int, update: TaskUpdate):
    """Update a task"""
    updates = {k: v for k, v in update.dict().items() if v is not None}
    
    if 'priority' in updates:
        updates['priority'] = Priority(updates['priority'])
    if 'status' in updates:
        updates['status'] = Status(updates['status'])
    if 'due_date' in updates and updates['due_date']:
        try:
            updates['due_date'] = datetime.fromisoformat(updates['due_date'])
        except:
            del updates['due_date']
    
    success = db.update_task(task_id, **updates)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found or no changes")
    return {"message": "Task updated successfully"}

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    """Archive a task"""
    success = db.delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task archived"}

@app.get("/api/stats")
def get_stats():
    """Get task statistics"""
    return db.get_stats()

@app.get("/api/categories")
def get_categories():
    """Get all categories"""
    return {"categories": db.get_categories()}

# Task Relationship Endpoints
@app.post("/api/tasks/{task_id}/relationships")
def add_relationship(task_id: int, relationship_type: str, related_task_id: int):
    """Create a relationship between tasks"""
    try:
        rel_type = RelationshipType(relationship_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid relationship type. Must be one of: {[r.value for r in RelationshipType]}")
    
    success = db.add_relationship(task_id, rel_type, related_task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Relationship already exists or invalid task IDs")
    return {"message": "Relationship created successfully"}

@app.get("/api/tasks/{task_id}/relationships")
def get_relationships(task_id: int, relationship_type: Optional[str] = None):
    """Get all relationships for a task"""
    rel_type = None
    if relationship_type:
        try:
            rel_type = RelationshipType(relationship_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid relationship type")
    
    relationships = db.get_related_tasks(task_id, rel_type)
    return {"relationships": relationships, "count": len(relationships)}

@app.delete("/api/tasks/{task_id}/relationships")
def delete_relationship(task_id: int, relationship_type: str, related_task_id: int):
    """Remove a relationship"""
    try:
        rel_type = RelationshipType(relationship_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid relationship type")
    
    success = db.delete_relationship(task_id, rel_type, related_task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Relationship not found")
    return {"message": "Relationship deleted successfully"}

@app.get("/api/blocked-tasks")
def get_blocked_tasks():
    """Get tasks that are blocked by incomplete dependencies"""
    return {"blocked_tasks": db.get_blocked_tasks()}

# Static UI
@app.get("/", response_class=HTMLResponse)
def get_ui():
    """Serve the TODO UI"""
    ui_path = os.path.join(os.path.dirname(__file__), 'index.html')
    if os.path.exists(ui_path):
        with open(ui_path) as f:
            return f.read()
    return "<h1>TODO System</h1><p>UI not found</p>"

@app.get("/journal.md")
def get_journal():
    """Serve the journal file"""
    journal_path = os.path.expanduser("~/.openclaw/workspace/JOURNAL.md")
    if os.path.exists(journal_path):
        return FileResponse(journal_path, media_type="text/markdown")
    raise HTTPException(status_code=404, detail="Journal not found")

@app.post("/api/journal/append")
def append_journal_entry(entry: dict):
    """Safely append a journal entry - API only, no direct file writes"""
    from datetime import datetime
    
    journal_path = os.path.expanduser("~/.openclaw/workspace/JOURNAL.md")
    
    # Read existing content first
    existing = ""
    if os.path.exists(journal_path):
        with open(journal_path, 'r') as f:
            existing = f.read()
    
    # Format new entry
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = entry.get('title', 'Untitled')
    content = entry.get('content', '')
    
    new_entry = f"\n\n---\n\n## Entry: {timestamp} UTC\n\n### {title}\n\n{content}\n"
    
    # Append safely
    with open(journal_path, 'a') as f:
        f.write(new_entry)
    
    return {"message": "Journal entry appended", "timestamp": timestamp}

@app.post("/api/tasks/{task_id}/edit")
def edit_task_description(task_id: int, edit: dict):
    """Edit a task's description - requires matching old text"""
    task = db.get_task_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    old_text = edit.get('old_text')
    new_text = edit.get('new_text')
    
    if not old_text or not new_text:
        raise HTTPException(status_code=400, detail="old_text and new_text required")
    
    current_desc = task.get('description', '')
    
    if old_text not in current_desc:
        raise HTTPException(status_code=400, detail="old_text not found in current description")
    
    updated_desc = current_desc.replace(old_text, new_text, 1)
    
    success = db.update_task(task_id, description=updated_desc)
    if success:
        return {"message": "Task edited successfully", "task_id": task_id}
    else:
        raise HTTPException(status_code=500, detail="Failed to update task")

@app.post("/api/journal/append-safe")
def append_journal_entry_safe(entry: dict):
    """Ultra-safe append with backup"""
    import shutil
    from datetime import datetime
    
    journal_path = os.path.expanduser("~/.openclaw/workspace/JOURNAL.md")
    backup_path = journal_path + ".backup"
    
    # Create backup first
    if os.path.exists(journal_path):
        shutil.copy2(journal_path, backup_path)
    
    try:
        # Format and append
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        title = entry.get('title', 'Untitled')
        content = entry.get('content', '')
        
        new_entry = f"\n\n---\n\n## Entry: {timestamp} UTC\n\n### {title}\n\n{content}\n"
        
        with open(journal_path, 'a') as f:
            f.write(new_entry)
        
        return {"message": "Journal entry appended safely", "timestamp": timestamp}
    except Exception as e:
        # Restore from backup on failure
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, journal_path)
        raise HTTPException(status_code=500, detail=f"Failed to append: {str(e)}")

@app.get("/avatar.png")
def get_avatar():
    """Serve the EverQuest avatar image"""
    avatar_path = os.path.expanduser("~/.openclaw/workspace/izzy_everquest_avatar.png")
    if os.path.exists(avatar_path):
        return FileResponse(avatar_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Avatar not found")

if __name__ == "__main__":
    print("📝 Starting TODO System...")
    print("📊 API: http://localhost:8000/api")
    print("🖥️  UI:  http://localhost:8000/")
    uvicorn.run(app, host="0.0.0.0", port=8000)
