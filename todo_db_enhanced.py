"""
Enhanced TODO Database with Automated Backups
SQLite with hourly backups to prevent data loss
"""

import sqlite3
import json
import shutil
import os
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = os.path.expanduser("~/.openclaw/workspace/todo.db")
BACKUP_DIR = os.path.expanduser("~/.openclaw/workspace/backups")

class TodoDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.backup_dir = Path(BACKUP_DIR)
        self.backup_dir.mkdir(exist_ok=True)
        self.init_db()
        self.auto_backup()
    
    def auto_backup(self):
        """Create backup if it's been more than 1 hour since last backup"""
        backup_marker = self.backup_dir / ".last_backup"
        
        should_backup = True
        if backup_marker.exists():
            last_backup = datetime.fromtimestamp(backup_marker.stat().st_mtime)
            if datetime.now() - last_backup < timedelta(hours=1):
                should_backup = False
        
        if should_backup:
            self.create_backup()
            backup_marker.touch()
    
    def create_backup(self):
        """Create timestamped backup of database"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"todo_backup_{timestamp}.db"
        
        # Create backup
        shutil.copy2(self.db_path, backup_path)
        
        # Keep only last 24 backups
        backups = sorted(self.backup_dir.glob("todo_backup_*.db"))
        if len(backups) > 24:
            for old_backup in backups[:-24]:
                old_backup.unlink()
        
        print(f"💾 Database backup created: {backup_path}")
        return backup_path
    
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
                    FOREIGN KEY (task_id) REFERENCES tasks(id),
                    UNIQUE(task_id, relationship_type, related_task_id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS journal_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

# Export for use in other modules
if __name__ == "__main__":
    db = TodoDB()
    print("✅ Enhanced TODO database initialized")
    print(f"   Database: {DB_PATH}")
    print(f"   Backups: {BACKUP_DIR}")
