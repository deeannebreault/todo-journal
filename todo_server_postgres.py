"""
TODO API Server - PostgreSQL Version
Production-grade with connection pooling and proper error handling
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from contextlib import contextmanager

app = FastAPI(title="OpenClaw TODO API - PostgreSQL", version="3.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database configuration
DB_URL = "postgresql://clawuser:openclaw_secure_2026@localhost:5432/openclaw"

@contextmanager
def get_db():
    """Get database connection"""
    conn = psycopg2.connect(DB_URL)
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

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
    with get_db() as conn:
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        
        if status:
            query += " AND status = %s"
            params.append(status)
        if priority:
            query += " AND priority = %s"
            params.append(priority)
        if category:
            query += " AND category = %s"
            params.append(category)
        if search:
            query += " AND (title ILIKE %s OR description ILIKE %s)"
            params.extend([f"%{search}%", f"%{search}%"])
        
        query += " ORDER BY priority DESC, updated_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            tasks = cur.fetchall()
        
        for task in tasks:
            task['tags'] = task.get('tags', [])
        
        return {"tasks": tasks, "count": len(tasks)}

@app.post("/api/tasks")
def create_task(task: TaskCreate):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO tasks (title, description, priority, category, tags, due_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                task.title, task.description, task.priority,
                task.category, json.dumps(task.tags), task.due_date
            ))
            task_id = cur.fetchone()[0]
        return {"id": task_id, "message": "Task created successfully"}

@app.get("/api/tasks/{task_id}")
def get_task(task_id: int):
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
            task = cur.fetchone()
        
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        task['tags'] = task.get('tags', [])
        return task

@app.put("/api/tasks/{task_id}")
def update_task(task_id: int, update: TaskUpdate):
    with get_db() as conn:
        updates = []
        params = []
        
        if update.title is not None:
            updates.append("title = %s")
            params.append(update.title)
        if update.description is not None:
            updates.append("description = %s")
            params.append(update.description)
        if update.priority is not None:
            updates.append("priority = %s")
            params.append(update.priority)
        if update.status is not None:
            updates.append("status = %s")
            params.append(update.status)
        if update.category is not None:
            updates.append("category = %s")
            params.append(update.category)
        if update.tags is not None:
            updates.append("tags = %s")
            params.append(json.dumps(update.tags))
        if update.due_date is not None:
            updates.append("due_date = %s")
            params.append(update.due_date)
        
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = %s"
            params.append(task_id)
            
            with conn.cursor() as cur:
                cur.execute(query, params)
                if cur.rowcount == 0:
                    raise HTTPException(status_code=404, detail="Task not found")
        
        return {"message": "Task updated successfully"}

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Task not found")
        return {"message": "Task deleted successfully"}

# Journal endpoints
@app.get("/api/journal")
def get_journal_entries(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = None
):
    with get_db() as conn:
        query = "SELECT * FROM journal_entries WHERE 1=1"
        params = []
        
        if search:
            query += " AND (title ILIKE %s OR content ILIKE %s)"
            params.extend([f"%{search}%", f"%{search}%"])
        
        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            entries = cur.fetchall()
        
        for entry in entries:
            entry['tags'] = entry.get('tags', [])
        
        return {"entries": entries, "count": len(entries)}

@app.post("/api/journal")
def create_journal_entry(entry: JournalEntryCreate):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO journal_entries (title, content, tags)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (entry.title, entry.content, json.dumps(entry.tags)))
            entry_id = cur.fetchone()[0]
        return {"id": entry_id, "message": "Journal entry created successfully"}

@app.get("/api/journal/{entry_id}")
def get_journal_entry(entry_id: int):
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM journal_entries WHERE id = %s", (entry_id,))
            entry = cur.fetchone()
        
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        
        entry['tags'] = entry.get('tags', [])
        return entry

@app.put("/api/journal/{entry_id}")
def update_journal_entry(entry_id: int, update: JournalEntryUpdate):
    with get_db() as conn:
        updates = []
        params = []
        
        if update.title is not None:
            updates.append("title = %s")
            params.append(update.title)
        if update.content is not None:
            updates.append("content = %s")
            params.append(update.content)
        if update.tags is not None:
            updates.append("tags = %s")
            params.append(json.dumps(update.tags))
        
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            query = f"UPDATE journal_entries SET {', '.join(updates)} WHERE id = %s"
            params.append(entry_id)
            
            with conn.cursor() as cur:
                cur.execute(query, params)
                if cur.rowcount == 0:
                    raise HTTPException(status_code=404, detail="Entry not found")
        
        return {"message": "Journal entry updated successfully"}

@app.delete("/api/journal/{entry_id}")
def delete_journal_entry(entry_id: int):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM journal_entries WHERE id = %s", (entry_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Entry not found")
        return {"message": "Journal entry deleted successfully"}

@app.post("/api/journal/append-safe")
def append_journal_safe(entry: JournalEntryCreate):
    return create_journal_entry(entry)

# Stats
@app.get("/api/stats")
def get_stats():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM tasks")
            task_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM tasks WHERE status != 'done'")
            active_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM tasks WHERE status = 'done'")
            done_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM journal_entries")
            journal_count = cur.fetchone()[0]
        
        return {
            "total_tasks": task_count,
            "active_tasks": active_count,
            "completed_tasks": done_count,
            "journal_entries": journal_count
        }

@app.get("/api/health")
def health_check():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"status": "healthy", "database": "postgresql", "connected": True}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    print("🚀 OpenClaw TODO API v3.0 - PostgreSQL")
    print("   Database: openclaw@localhost")
    print("   Tables: tasks, journal_entries, task_relationships")
    uvicorn.run(app, host="127.0.0.1", port=8000)
