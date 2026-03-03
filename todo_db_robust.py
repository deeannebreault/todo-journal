#!/usr/bin/env python3
"""
Enhanced SQLite Database for TODO/Journal with Production-Grade Reliability
Uses WAL mode, automated backups, and corruption detection
"""

import sqlite3
import shutil
import os
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import contextmanager
import threading
import time

DB_PATH = Path(os.path.expanduser("~/.openclaw/workspace/todo.db"))
BACKUP_DIR = Path(os.path.expanduser("~/.openclaw/workspace/backups"))
JOURNAL_PATH = Path(os.path.expanduser("~/.openclaw/workspace/JOURNAL.md"))

class RobustDatabase:
    """Production-grade SQLite with WAL, backups, and integrity checks"""
    
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.backup_dir = BACKUP_DIR
        self.backup_dir.mkdir(exist_ok=True)
        self.lock = threading.Lock()
        
        # Initialize database
        self._init_db()
        self._enable_wal_mode()
        self._start_backup_thread()
    
    def _init_db(self):
        """Create tables with foreign keys and indexes"""
        with self._get_connection() as conn:
            # Tasks table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    priority INTEGER DEFAULT 2 CHECK (priority BETWEEN 1 AND 4),
                    status TEXT DEFAULT 'todo' CHECK (status IN ('todo', 'in_progress', 'done')),
                    category TEXT DEFAULT 'general',
                    tags TEXT DEFAULT '[]',
                    due_date TIMESTAMP,
                    parent_id INTEGER,
                    created_at TIMESTAMP DEFAULT (datetime('now')),
                    updated_at TIMESTAMP DEFAULT (datetime('now')),
                    FOREIGN KEY (parent_id) REFERENCES tasks(id) ON DELETE SET NULL
                )
            """)
            
            # Journal entries table - REAL persistence, not file-based
            conn.execute("""
                CREATE TABLE IF NOT EXISTS journal_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT (datetime('now')),
                    updated_at TIMESTAMP DEFAULT (datetime('now'))
                )
            """)
            
            # Task relationships
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    related_task_id INTEGER NOT NULL,
                    relationship_type TEXT NOT NULL CHECK (
                        relationship_type IN ('completed_before', 'parent', 'child', 
                                             'depends_on', 'subsumes', 'blocks', 'related')
                    ),
                    created_at TIMESTAMP DEFAULT (datetime('now')),
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY (related_task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    UNIQUE(task_id, relationship_type, related_task_id)
                )
            """)
            
            # Indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks(category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_updated ON tasks(updated_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_created ON journal_entries(created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_relationships_task ON task_relationships(task_id)")
            
            # Backup log table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS backup_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_path TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT (datetime('now'))
                )
            """)
    
    def _enable_wal_mode(self):
        """Enable Write-Ahead Logging for better concurrency and safety"""
        with self._get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with proper settings"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _start_backup_thread(self):
        """Start background backup thread"""
        def backup_worker():
            while True:
                time.sleep(3600)  # Backup every hour
                try:
                    self.create_backup()
                except Exception as e:
                    print(f"Backup failed: {e}")
        
        thread = threading.Thread(target=backup_worker, daemon=True)
        thread.start()
    
    def create_backup(self) -> Path:
        """Create timestamped backup with integrity verification"""
        with self.lock:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.backup_dir / f"todo_backup_{timestamp}.db"
            
            # Create backup
            with self._get_connection() as conn:
                # Verify integrity first
                result = conn.execute("PRAGMA integrity_check").fetchone()[0]
                if result != "ok":
                    raise Exception(f"Database integrity check failed: {result}")
                
                # Create backup using SQLite's backup API
                backup_conn = sqlite3.connect(backup_path)
                conn.backup(backup_conn)
                backup_conn.close()
            
            # Calculate checksum
            with open(backup_path, 'rb') as f:
                checksum = hashlib.sha256(f.read()).hexdigest()[:16]
            
            # Log backup
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO backup_log (backup_path, checksum) VALUES (?, ?)",
                    (str(backup_path), checksum)
                )
            
            # Keep only last 24 backups
            backups = sorted(self.backup_dir.glob("todo_backup_*.db"))
            if len(backups) > 24:
                for old_backup in backups[:-24]:
                    old_backup.unlink()
            
            print(f"💾 Backup created: {backup_path.name} (checksum: {checksum})")
            return backup_path
    
    def verify_integrity(self) -> bool:
        """Check database integrity"""
        with self._get_connection() as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            return result == "ok"
    
    def migrate_from_file_journal(self):
        """Migrate JOURNAL.md entries to database"""
        if not JOURNAL_PATH.exists():
            print("No JOURNAL.md found to migrate")
            return
        
        with open(JOURNAL_PATH) as f:
            content = f.read()
        
        # Parse entries
        entries = []
        current = None
        
        for line in content.split('\n'):
            if line.startswith('## Entry'):
                if current:
                    entries.append(current)
                title = line.replace('## Entry', '').strip()
                current = {'title': title, 'content': ''}
            elif current:
                current['content'] += line + '\n'
        
        if current:
            entries.append(current)
        
        # Insert into database
        with self._get_connection() as conn:
            for entry in entries:
                try:
                    conn.execute("""
                        INSERT INTO journal_entries (title, content)
                        VALUES (?, ?)
                        ON CONFLICT DO NOTHING
                    """, (entry['title'], entry['content'].strip()))
                except Exception as e:
                    print(f"Failed to migrate entry: {e}")
        
        print(f"✅ Migrated {len(entries)} journal entries to database")

# Singleton instance
db = None

def get_db() -> RobustDatabase:
    """Get database singleton"""
    global db
    if db is None:
        db = RobustDatabase()
    return db

if __name__ == "__main__":
    db = get_db()
    print("✅ Enhanced database initialized")
    print(f"   Path: {DB_PATH}")
    print(f"   Backups: {BACKUP_DIR}")
    print(f"   WAL mode: Enabled")
    print(f"   Auto-backup: Every hour")
    
    # Verify integrity
    if db.verify_integrity():
        print("   Integrity: ✓ OK")
    else:
        print("   Integrity: ✗ CORRUPTED")
    
    # Migrate existing journal
    db.migrate_from_file_journal()
