"""
TODO System - Database Models and API
SQLite-based, FastAPI backend, priority: MEDIUM
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
import os

DB_PATH = os.path.expanduser("~/.openclaw/workspace/todo.db")

class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

class Status(Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    ARCHIVED = "archived"

@dataclass
class Task:
    id: Optional[int]
    title: str
    description: str
    priority: Priority
    status: Status
    created_at: datetime
    updated_at: datetime
    due_date: Optional[datetime]
    tags: List[str]
    category: str
    parent_id: Optional[int]

class RelationshipType(Enum):
    COMPLETED_BEFORE = "completed_before"
    PARENT = "parent"
    CHILD = "child"
    DEPENDS_ON = "depends_on"
    SUBSUMES = "subsumes"
    BLOCKS = "blocks"
    RELATED = "related"

@dataclass
class TaskRelationship:
    id: Optional[int]
    task_id: int
    relationship_type: RelationshipType
    related_task_id: int
    created_at: datetime

class TodoDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Create tables if they don't exist"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    priority INTEGER DEFAULT 2,
                    status TEXT DEFAULT 'todo',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    due_date TIMESTAMP,
                    tags TEXT DEFAULT '[]',
                    category TEXT DEFAULT 'general',
                    parent_id INTEGER,
                    FOREIGN KEY (parent_id) REFERENCES tasks(id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER,
                    action TEXT,
                    old_value TEXT,
                    new_value TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    relationship_type TEXT NOT NULL,
                    related_task_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY (related_task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    UNIQUE(task_id, relationship_type, related_task_id)
                )
            """)
            
            conn.commit()
    
    def add_task(self, title: str, description: str = "", 
                 priority: Priority = Priority.MEDIUM,
                 category: str = "general",
                 tags: List[str] = None,
                 due_date: Optional[datetime] = None,
                 parent_id: Optional[int] = None) -> int:
        """Add a new task"""
        tags = tags or []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO tasks (title, description, priority, status, 
                                 due_date, tags, category, parent_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (title, description, priority.value, Status.TODO.value,
                  due_date.isoformat() if due_date else None,
                  json.dumps(tags), category, parent_id))
            conn.commit()
            return cursor.lastrowid
    
    def get_tasks(self, status: Optional[Status] = None,
                  priority: Optional[Priority] = None,
                  category: Optional[str] = None,
                  tags: List[str] = None,
                  search: Optional[str] = None) -> List[dict]:
        """Get tasks with optional filters"""
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        
        if status:
            query += " AND status = ?"
            params.append(status.value)
        if priority:
            query += " AND priority = ?"
            params.append(priority.value)
        if category:
            query += " AND category = ?"
            params.append(category)
        if search:
            query += " AND (title LIKE ? OR description LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        
        query += " ORDER BY priority DESC, created_at DESC"
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            tasks = []
            for row in rows:
                task = dict(row)
                task['tags'] = json.loads(task['tags'])
                tasks.append(task)
            return tasks
    
    def update_task(self, task_id: int, **kwargs) -> bool:
        """Update task fields"""
        allowed_fields = ['title', 'description', 'priority', 'status', 
                         'due_date', 'tags', 'category']
        updates = []
        params = []
        
        for field, value in kwargs.items():
            if field in allowed_fields:
                updates.append(f"{field} = ?")
                if field == 'tags':
                    params.append(json.dumps(value))
                elif field == 'priority' and isinstance(value, Priority):
                    params.append(value.value)
                elif field == 'status' and isinstance(value, Status):
                    params.append(value.value)
                else:
                    params.append(value)
        
        if not updates:
            return False
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(task_id)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"""
                UPDATE tasks SET {', '.join(updates)} WHERE id = ?
            """, params)
            conn.commit()
            return True
    
    def delete_task(self, task_id: int) -> bool:
        """Soft delete (archive) a task"""
        return self.update_task(task_id, status=Status.ARCHIVED)
    
    def get_stats(self) -> dict:
        """Get task statistics"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT status, priority, COUNT(*) as count 
                FROM tasks 
                GROUP BY status, priority
            """)
            return {
                'by_status': cursor.fetchall(),
                'total': conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
                'active': conn.execute(
                    "SELECT COUNT(*) FROM tasks WHERE status NOT IN ('done', 'archived')"
                ).fetchone()[0]
            }
    
    def get_categories(self) -> List[str]:
        """Get all unique categories"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT category FROM tasks ORDER BY category"
            ).fetchall()
            return [row[0] for row in rows]

    # Task Relationship Methods
    def add_relationship(self, task_id: int, relationship_type: RelationshipType, 
                         related_task_id: int) -> bool:
        """Create a relationship between two tasks"""
        if task_id == related_task_id:
            return False  # Can't relate a task to itself
        
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute("""
                    INSERT INTO task_relationships (task_id, relationship_type, related_task_id)
                    VALUES (?, ?, ?)
                """, (task_id, relationship_type.value, related_task_id))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False  # Relationship already exists
    
    def get_relationships(self, task_id: int) -> List[dict]:
        """Get all relationships for a task"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT r.*, t.title as related_title
                FROM task_relationships r
                JOIN tasks t ON r.related_task_id = t.id
                WHERE r.task_id = ? AND t.status != 'archived'
            """, (task_id,)).fetchall()
            return [dict(row) for row in rows]
    
    def get_related_tasks(self, task_id: int, relationship_type: Optional[RelationshipType] = None) -> List[dict]:
        """Get all tasks related to a specific task"""
        query = """
            SELECT t.*, r.relationship_type, r.task_id as source_id
            FROM task_relationships r
            JOIN tasks t ON r.related_task_id = t.id
            WHERE r.task_id = ? AND t.status != 'archived'
        """
        params = [task_id]
        
        if relationship_type:
            query += " AND r.relationship_type = ?"
            params.append(relationship_type.value)
        
        query += " ORDER BY t.priority DESC, t.created_at DESC"
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            tasks = []
            for row in rows:
                task = dict(row)
                task['tags'] = json.loads(task['tags'])
                task['relationship_type'] = row['relationship_type']
                task['is_related_from'] = row['source_id'] == task_id
                tasks.append(task)
            return tasks
    
    def delete_relationship(self, task_id: int, relationship_type: RelationshipType, 
                            related_task_id: int) -> bool:
        """Remove a relationship between tasks"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM task_relationships 
                WHERE task_id = ? AND relationship_type = ? AND related_task_id = ?
            """, (task_id, relationship_type.value, related_task_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_blocked_tasks(self) -> List[dict]:
        """Get tasks that are blocked by other incomplete tasks"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT t.*, blocker.title as blocker_title, blocker.id as blocker_id
                FROM task_relationships r
                JOIN tasks t ON r.task_id = t.id
                JOIN tasks blocker ON r.related_task_id = blocker.id
                WHERE r.relationship_type = 'depends_on'
                  AND t.status IN ('todo', 'in_progress')
                  AND blocker.status != 'done'
            """).fetchall()
            return [dict(row) for row in rows]

# Initialize database
db = TodoDB()

if __name__ == "__main__":
    # Add sample tasks
    db.add_task("Review arrows.app deployment", 
                priority=Priority.HIGH,
                category="deployment",
                tags=["github", "pages"])
    
    db.add_task("Continue LadybugDB pipeline integration",
                priority=Priority.HIGH, 
                category="backend",
                tags=["ladybug", "database"])
    
    db.add_task("Schedule eye appointment",
                priority=Priority.MEDIUM,
                category="personal",
                tags=["health", "appointment"])
    
    db.add_task("Build TODO system UI",
                priority=Priority.MEDIUM,
                category="feature",
                tags=["ui", "productivity"])
    
    print("Database initialized with sample tasks!")
    print(f"Stats: {db.get_stats()}")
