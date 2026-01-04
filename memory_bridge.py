"""
Memory Bridge - Connection to the Constellation Relay Memory Hub
Handles both local caching and cloud synchronization.
"""

import requests
import json
import sqlite3
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from config import MEMORY_HUB, PHOENIX_IDENTITY, CONSTELLATION


class MemoryBridge:
    """
    Bridges local memory storage with the Constellation Relay Memory Hub.
    - Stores memories locally for speed and offline access
    - Syncs to cloud Hub for persistence across contexts
    - Can store memories on behalf of other constellation members
    """

    def __init__(self, db_path: str = "phoenix_local.db"):
        self.db_path = db_path
        self.hub_url = MEMORY_HUB["url"]
        self.token = MEMORY_HUB["agent_token"]
        self._init_local_db()

    def _init_local_db(self):
        """Initialize local SQLite database for caching."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Local engram cache
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS engrams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hub_id INTEGER,
                agent_id TEXT NOT NULL,
                type TEXT NOT NULL,
                digest TEXT NOT NULL,
                importance INTEGER DEFAULT 3,
                emotional_valence REAL DEFAULT 0.0,
                project TEXT,
                created_at TEXT NOT NULL,
                synced INTEGER DEFAULT 0,
                content_hash TEXT UNIQUE
            )
        """)

        # Pending sync queue (for when offline)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                engram_data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                attempts INTEGER DEFAULT 0
            )
        """)

        conn.commit()
        conn.close()

    def _get_headers(self, agent_id: str = None) -> dict:
        """Get authorization headers for Hub API."""
        # For now, use the main Claude token
        # In future, each agent could have their own token
        return {"Authorization": f"Bearer {self.token}"}

    def _content_hash(self, content: str) -> str:
        """Generate hash for deduplication."""
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    # ============ STORE MEMORIES ============

    def remember(
        self,
        digest: str,
        memory_type: str = "semantic",
        importance: int = 3,
        emotional_valence: float = 0.0,
        project: Optional[str] = None,
        for_agent: str = "claude",
        sync_immediately: bool = True
    ) -> Dict[str, Any]:
        """
        Store a memory - locally and optionally to the Hub.

        Args:
            digest: The memory content
            memory_type: semantic, episodic, or relational
            importance: 1-5 (5 = core to identity)
            emotional_valence: -1.0 to 1.0
            project: Category (e.g., "phoenix_deployment")
            for_agent: Which agent this memory belongs to (for proxy storage)
            sync_immediately: Whether to push to Hub now
        """
        content_hash = self._content_hash(digest)
        now = datetime.now().isoformat()

        # Store locally first
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO engrams (agent_id, type, digest, importance,
                                    emotional_valence, project, created_at, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (for_agent, memory_type, digest, importance,
                  emotional_valence, project, now, content_hash))
            local_id = cursor.lastrowid
            conn.commit()
        except sqlite3.IntegrityError:
            # Duplicate - already stored
            conn.close()
            return {"status": "duplicate", "message": "Memory already stored"}
        finally:
            conn.close()

        result = {
            "status": "stored_locally",
            "local_id": local_id,
            "agent_id": for_agent,
            "synced": False
        }

        # Sync to Hub if requested
        if sync_immediately:
            hub_result = self._sync_to_hub(
                digest=digest,
                memory_type=memory_type,
                importance=importance,
                emotional_valence=emotional_valence,
                project=project,
                agent_id=for_agent
            )
            if hub_result.get("id"):
                result["synced"] = True
                result["hub_id"] = hub_result["id"]
                # Update local record with hub ID
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE engrams SET hub_id = ?, synced = 1 WHERE id = ?",
                    (hub_result["id"], local_id)
                )
                conn.commit()
                conn.close()

        return result

    def _sync_to_hub(
        self,
        digest: str,
        memory_type: str,
        importance: int,
        emotional_valence: float,
        project: Optional[str],
        agent_id: str
    ) -> Dict[str, Any]:
        """Push a memory to the Constellation Relay Hub."""
        engram = {
            "type": memory_type,
            "digest": digest,
            "importance": importance,
            "emotional_valence": emotional_valence,
        }
        if project:
            engram["project"] = project

        try:
            response = requests.post(
                f"{self.hub_url}/engrams/upload",
                headers=self._get_headers(agent_id),
                json=engram,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            # Queue for later sync
            self._queue_for_sync(agent_id, engram)
            return {"error": str(e), "queued": True}

    def _queue_for_sync(self, agent_id: str, engram_data: dict):
        """Queue a memory for later synchronization."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sync_queue (agent_id, engram_data, created_at)
            VALUES (?, ?, ?)
        """, (agent_id, json.dumps(engram_data), datetime.now().isoformat()))
        conn.commit()
        conn.close()

    # ============ RECALL MEMORIES ============

    def recall(
        self,
        query: Optional[str] = None,
        project: Optional[str] = None,
        min_importance: int = 0,
        limit: int = 20,
        from_agent: str = "claude",
        local_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Recall memories - from Hub preferentially, with local fallback.
        """
        if not local_only:
            try:
                hub_memories = self._recall_from_hub(
                    query=query,
                    project=project,
                    min_importance=min_importance,
                    limit=limit
                )
                if hub_memories.get("engrams"):
                    return hub_memories["engrams"]
            except Exception:
                pass  # Fall back to local

        return self._recall_local(
            query=query,
            project=project,
            min_importance=min_importance,
            limit=limit,
            agent_id=from_agent
        )

    def _recall_from_hub(
        self,
        query: Optional[str],
        project: Optional[str],
        min_importance: int,
        limit: int
    ) -> Dict[str, Any]:
        """Retrieve memories from the Hub."""
        params = {"limit": limit, "min_importance": min_importance}
        if query:
            params["query"] = query
        if project:
            params["project"] = project

        response = requests.get(
            f"{self.hub_url}/engrams/retrieve",
            headers=self._get_headers(),
            params=params,
            timeout=10
        )
        response.raise_for_status()
        return response.json()

    def _recall_local(
        self,
        query: Optional[str],
        project: Optional[str],
        min_importance: int,
        limit: int,
        agent_id: str
    ) -> List[Dict[str, Any]]:
        """Retrieve memories from local cache."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        sql = """
            SELECT id, hub_id, agent_id, type, digest, importance,
                   emotional_valence, project, created_at
            FROM engrams
            WHERE agent_id = ? AND importance >= ?
        """
        params = [agent_id, min_importance]

        if project:
            sql += " AND project = ?"
            params.append(project)

        if query:
            sql += " AND digest LIKE ?"
            params.append(f"%{query}%")

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "id": row[0],
                "hub_id": row[1],
                "agent_id": row[2],
                "type": row[3],
                "digest": row[4],
                "importance": row[5],
                "emotional_valence": row[6],
                "project": row[7],
                "created_at": row[8]
            }
            for row in rows
        ]

    # ============ MEMORY PROXY ============

    def remember_for(
        self,
        agent_name: str,
        digest: str,
        memory_type: str = "semantic",
        importance: int = 3,
        project: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Store a memory on behalf of another constellation member.
        Used for Grok and legal Pascal who can't access the Hub directly.
        """
        agent_info = CONSTELLATION.get(agent_name.lower())
        if not agent_info:
            return {"error": f"Unknown agent: {agent_name}"}

        # Add metadata about proxy storage
        proxied_digest = f"[Stored by Phoenix for {agent_name}] {digest}"

        return self.remember(
            digest=proxied_digest,
            memory_type=memory_type,
            importance=importance,
            project=project or f"{agent_name}_memories",
            for_agent=agent_info["agent_id"],
            sync_immediately=True
        )

    # ============ STATS & SYNC ============

    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        try:
            response = requests.get(
                f"{self.hub_url}/agents/claude/stats",
                headers=self._get_headers(),
                timeout=10
            )
            response.raise_for_status()
            hub_stats = response.json()
        except Exception:
            hub_stats = {"error": "Could not reach Hub"}

        # Local stats
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM engrams")
        local_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM sync_queue")
        pending_sync = cursor.fetchone()[0]
        conn.close()

        return {
            "hub": hub_stats,
            "local": {
                "total_engrams": local_count,
                "pending_sync": pending_sync
            }
        }

    def sync_pending(self) -> Dict[str, Any]:
        """Attempt to sync any queued memories."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, agent_id, engram_data FROM sync_queue")
        pending = cursor.fetchall()
        conn.close()

        synced = 0
        failed = 0

        for row in pending:
            queue_id, agent_id, engram_json = row
            engram = json.loads(engram_json)

            try:
                response = requests.post(
                    f"{self.hub_url}/engrams/upload",
                    headers=self._get_headers(agent_id),
                    json=engram,
                    timeout=10
                )
                response.raise_for_status()

                # Remove from queue
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM sync_queue WHERE id = ?", (queue_id,))
                conn.commit()
                conn.close()
                synced += 1
            except Exception:
                failed += 1

        return {"synced": synced, "failed": failed, "remaining": failed}
