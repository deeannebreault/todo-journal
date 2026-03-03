"""
TODO API Server - Enhanced Version with Robust Database
Supports tasks and journal entries with proper persistence
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import json
import uvicorn
from pathlib import Path
import sys

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent))

from todo_db_robust import get_db

app = FastAPI(title="OpenClaw TODO API", version="2.0.0")

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get database instance
db = get_db()

# Pydantic models
class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    priority: int = 2
    category: str = "general"
    tags: List[str] = []
    due_date: Optional[str] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    status: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    due_date: Optional[str] = None

class JournalEntryCreate(BaseModel):
    title: str
    content: str
    tags: List[str] = []

class JournalEntryUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None

# Task endpoints
@app.get("/api/tasks")
def get_tasks(
    status: Optional[str] = None,
    priority: Optional[int] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """Get tasks with optional filtering"""
    with db._get_connection() as conn:
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        
        if status:
            query += " AND status = ?"
            params.append(status)
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        if category:
            query += " AND category = ?"
            params.append(category)
        if search:
            query += " AND (title LIKE ? OR description LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        
        query += " ORDER BY priority DESC, updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor = conn.execute(query, params)
        tasks = [dict(row) for row in cursor.fetchall()]
        
        # Parse tags JSON
        for task in tasks:
            task['tags'] = json.loads(task.get('tags', '[]'))
        
        return {"tasks": tasks, "count": len(tasks)}

@app.post("/api/tasks")
def create_task(task: TaskCreate):
    """Create a new task"""
    with db._get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO tasks (title, description, priority, category, tags, due_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            task.title,
            task.description,
            task.priority,
            task.category,
            json.dumps(task.tags),
            task.due_date
        ))
        task_id = cursor.lastrowid
        
        return {"id": task_id, "message": "Task created successfully"}

@app.get("/api/tasks/{task_id}")
def get_task(task_id: int):
    """Get a specific task"""
    with db._get_connection() as conn:
        cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        
        task = dict(row)
        task['tags'] = json.loads(task.get('tags', '[]'))
        return task

@app.put("/api/tasks/{task_id}")
def update_task(task_id: int, update: TaskUpdate):
    """Update a task"""
    with db._get_connection() as conn:
        # Check if task exists
        cursor = conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Task not found")
        
        # Build update query
        updates = []
        params = []
        
        if update.title is not None:
            updates.append("title = ?")
            params.append(update.title)
        if update.description is not None:
            updates.append("description = ?")
            params.append(update.description)
        if update.priority is not None:
            updates.append("priority = ?")
            params.append(update.priority)
        if update.status is not None:
            updates.append("status = ?")
            params.append(update.status)
        if update.category is not None:
            updates.append("category = ?")
            params.append(update.category)
        if update.tags is not None:
            updates.append("tags = ?")
            params.append(json.dumps(update.tags))
        if update.due_date is not None:
            updates.append("due_date = ?")
            params.append(update.due_date)
        
        if updates:
            updates.append("updated_at = datetime('now')")
            query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"
            params.append(task_id)
            conn.execute(query, params)
        
        return {"message": "Task updated successfully"}

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    """Delete a task"""
    with db._get_connection() as conn:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task not found")
        
        return {"message": "Task deleted successfully"}

# Journal endpoints
@app.get("/api/journal")
def get_journal_entries(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = None
):
    """Get journal entries"""
    with db._get_connection() as conn:
        query = "SELECT * FROM journal_entries WHERE 1=1"
        params = []
        
        if search:
            query += " AND (title LIKE ? OR content LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor = conn.execute(query, params)
        entries = [dict(row) for row in cursor.fetchall()]
        
        for entry in entries:
            entry['tags'] = json.loads(entry.get('tags', '[]'))
        
        return {"entries": entries, "count": len(entries)}

@app.post("/api/journal")
def create_journal_entry(entry: JournalEntryCreate):
    """Create a new journal entry"""
    with db._get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO journal_entries (title, content, tags)
            VALUES (?, ?, ?)
        """, (
            entry.title,
            entry.content,
            json.dumps(entry.tags)
        ))
        entry_id = cursor.lastrowid
        
        return {"id": entry_id, "message": "Journal entry created successfully"}

@app.get("/api/journal/{entry_id}")
def get_journal_entry(entry_id: int):
    """Get a specific journal entry"""
    with db._get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM journal_entries WHERE id = ?", 
            (entry_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Entry not found")
        
        entry = dict(row)
        entry['tags'] = json.loads(entry.get('tags', '[]'))
        return entry

@app.put("/api/journal/{entry_id}")
def update_journal_entry(entry_id: int, update: JournalEntryUpdate):
    """Update a journal entry"""
    with db._get_connection() as conn:
        cursor = conn.execute(
            "SELECT id FROM journal_entries WHERE id = ?", 
            (entry_id,)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Entry not found")
        
        updates = []
        params = []
        
        if update.title is not None:
            updates.append("title = ?")
            params.append(update.title)
        if update.content is not None:
            updates.append("content = ?")
            params.append(update.content)
        if update.tags is not None:
            updates.append("tags = ?")
            params.append(json.dumps(update.tags))
        
        if updates:
            updates.append("updated_at = datetime('now')")
            query = f"UPDATE journal_entries SET {', '.join(updates)} WHERE id = ?"
            params.append(entry_id)
            conn.execute(query, params)
        
        return {"message": "Journal entry updated successfully"}

@app.delete("/api/journal/{entry_id}")
def delete_journal_entry(entry_id: int):
    """Delete a journal entry"""
    with db._get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM journal_entries WHERE id = ?", 
            (entry_id,)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Entry not found")
        
        return {"message": "Journal entry deleted successfully"}

# Legacy endpoint for compatibility
@app.post("/api/journal/append-safe")
def append_journal_safe(entry: JournalEntryCreate):
    """Legacy compatibility endpoint - now creates proper DB entry"""
    return create_journal_entry(entry)

# Stats endpoint
@app.get("/api/stats")
def get_stats():
    """Get database statistics"""
    with db._get_connection() as conn:
        task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        active_count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status != 'done'"
        ).fetchone()[0]
        done_count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'done'"
        ).fetchone()[0]
        journal_count = conn.execute(
            "SELECT COUNT(*) FROM journal_entries"
        ).fetchone()[0]
        
        return {
            "total_tasks": task_count,
            "active_tasks": active_count,
            "completed_tasks": done_count,
            "journal_entries": journal_count
        }

# Health check
@app.get("/api/health")
def health_check():
    """Health check endpoint"""
    try:
        db.verify_integrity()
        return {
            "status": "healthy",
            "database": "ok",
            "wal_mode": True,
            "backups_enabled": True
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

if __name__ == "__main__":
    print("🚀 Starting OpenClaw TODO API v2.0")
    print("   Features: Tasks + Journal in database")
    print("   Backups: Enabled (hourly)")
    print("   WAL Mode: Enabled")
    uvicorn.run(app, host="127.0.0.1", port=8000)
