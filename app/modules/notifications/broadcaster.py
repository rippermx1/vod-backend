
import asyncio
import logging
from typing import Dict, Set
from uuid import UUID

logger = logging.getLogger(__name__)

class NotificationBroadcaster:
    def __init__(self):
        # Map user_id -> Change of connected queues
        # A user might have multiple tabs open, so we need a set of queues
        self.connections: Dict[UUID, Set[asyncio.Queue]] = {}
        self.lock = asyncio.Lock()

    async def connect(self, user_id: UUID) -> asyncio.Queue:
        """
        Create a new queue for a user connection.
        """
        async with self.lock:
            if user_id not in self.connections:
                self.connections[user_id] = set()
            
            queue = asyncio.Queue()
            self.connections[user_id].add(queue)
            logger.info(f"[Broadcaster] User {user_id} connected. Total connections: {len(self.connections[user_id])}")
            return queue

    async def disconnect(self, user_id: UUID, queue: asyncio.Queue):
        """
        Remove a queue when client disconnects.
        """
        async with self.lock:
            if user_id in self.connections:
                self.connections[user_id].discard(queue)
                if not self.connections[user_id]:
                    del self.connections[user_id]
                logger.info(f"[Broadcaster] User {user_id} disconnected.")

    async def broadcast(self, user_id: UUID, message: dict):
        """
        Push a message to all active connections for a user.
        """
        async with self.lock:
            queues = self.connections.get(user_id)
            if not queues:
                # User not connected, skip (or maybe push to DB only, which is done elsewhere)
                return

            logger.info(f"[Broadcaster] Pushing message to {user_id} ({len(queues)} queues)")
            for q in queues:
                await q.put(message)

# Global Instance
broadcaster = NotificationBroadcaster()
