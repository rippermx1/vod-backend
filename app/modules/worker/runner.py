
import asyncio
import logging
from typing import Callable, Any, Dict
from uuid import UUID

logger = logging.getLogger(__name__)

class Worker:
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.is_running = False
        self._task = None

    async def start(self):
        """Starts the worker loop."""
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._process_queue())
        logger.info("[Worker] Started.")

    async def stop(self):
        """Stops the worker loop."""
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[Worker] Stopped.")

    async def enqueue_job(self, task_name: str, **kwargs):
        """Adds a job to the queue."""
        logger.info(f"[Worker] Enqueuing job: {task_name} | Args: {kwargs}")
        await self.queue.put((task_name, kwargs))

    async def _process_queue(self):
        """Main loop consuming jobs."""
        from app.modules.transcoding.service import Transcoder
        # Import here to avoid circular imports if any, or dependency issues at module level
        
        while self.is_running:
            try:
                task_name, kwargs = await self.queue.get()
                
                logger.info(f"[Worker] Processing: {task_name}")
                
                try:
                    if task_name == "transcode_media":
                        media_id = kwargs.get("media_id")
                        if media_id:
                            # We need a DB session. 
                            # Since this is async/simulated, we need to create a session manually.
                            # Ideally Transcoder handles it or we pass a session factory?
                            # Let's assume Transcoder.process_media_job creates its own session or takes a session maker.
                            await Transcoder.process_media_job(media_id)
                            
                except Exception as e:
                    logger.error(f"[Worker] Job Failed: {e}", exc_info=True)
                finally:
                    self.queue.task_done()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Worker] Loop Error: {e}")
                await asyncio.sleep(1)

# Global Worker Instance
worker = Worker()
