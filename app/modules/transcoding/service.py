
import os
import asyncio
import shutil
import logging
from uuid import UUID
from datetime import datetime
from core.db import SessionLocal
from modules.cms import models
from sqlalchemy import select
from pathlib import Path

logger = logging.getLogger(__name__)

# Temp dir for processing
TRANSCODE_DIR = Path("c:/vod-saas/tmp/transcoding")

class Transcoder:
    @staticmethod
    async def process_media_job(media_id: UUID):
        """
        Job entry point. Creates a DB session and runs the pipeline.
        """
        async with SessionLocal() as db:
            media = await db.get(models.Media, media_id)
            if not media:
                logger.error(f"[Transcoder] Media {media_id} not found.")
                return

            try:
                logger.info(f"[Transcoder] Starting for {media.id} ({media.filename})")
                
                # Update status
                # media.processing_status = models.ProcessingStatus.PROCESSING
                # await db.commit()
                
                # Run Pipeline
                processor = MediaProcessor(media, db)
                new_path = await processor.run()
                
                # Update media path to point to the master playlist
                if new_path:
                    media.file_path = new_path
                    # media.processing_status = models.ProcessingStatus.READY 
                    # (Status update logic might be redundant if caller handles it, but Transcoder should probably mark READY?)
                    # The previous logic relied on notification or caller? 
                    # Let's set it to READY here to be sure.
                    media.processing_status = models.ProcessingStatus.READY
                    await db.commit()
                    
                    # Notify User
                    from modules.notifications import service as notification_service
                    await notification_service.create_notification(
                        db,
                        user_id=media.creator_id,
                        title="Media Ready",
                        message=f"Your video '{media.filename}' has finished processing.",
                        resource_type="media",
                        resource_id=media.id
                    )
                
                logger.info(f"[Transcoder] Success for {media.id}. New Path: {new_path}")
                
            except Exception as e:
                logger.error(f"[Transcoder] Failed: {e}", exc_info=True)
                await db.rollback() # Reset transaction
                media.processing_status = models.ProcessingStatus.FAILED
                await db.commit()

class MediaProcessor:
    def __init__(self, media: models.Media, db):
        self.media = media
        self.db = db
        self.work_dir = TRANSCODE_DIR / str(media.id)
        self.source_path = None
        
    async def run(self):
        # Setup
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # 1. Download / Locate Source
            self.source_path = await self._locate_source()
            
            # 2. Analyze (Probe) - Optional for now, assuming valid video
            
            # 3. Generate HLS Variants
            # We will generate a master playlist and 3 qualities (1080, 720, 480)
            # For efficiency in dev, maybe just 1 variant?
            # Let's do at least 2 to prove HLS concept (e.g. 720p and 480p)
            
            hls_dir = self.work_dir / "hls"
            hls_dir.mkdir(exist_ok=True)
            
            await self._transcode_hls(hls_dir)
            
            # 4. Generate Thumbnail
            thumb_path = self.work_dir / "poster.jpg"
            await self._generate_thumbnail(thumb_path)
            
            # 5. Upload / Move to Permanent Storage
            final_hls_path = await self._upload_results(hls_dir, thumb_path)
            
            # 6. Update DB
            self.media.file_path = final_hls_path # Point to master.m3u8
            self.media.processing_status = models.ProcessingStatus.READY
            # Maybe store thumbnail path in metadata or separate field?
            # For now, MVP assumes standard structure or cover_image_url on Content content-type usage.
            # Ideally Media has `thumbnail_url`.
            
            await self.db.commit()
            
            # Send Notification
            try:
                from modules.notifications import service as notif_service
                await notif_service.create_notification(
                    self.db,
                    self.media.creator_id,
                    "Media Ready",
                    f"Your video '{self.media.filename}' is ready to watch.",
                    resource_type="media",
                    resource_id=str(self.media.id)
                )
            except Exception as e:
                # Don't fail job if notification fails
                import logging
                logging.getLogger(__name__).error(f"Failed to send notification: {e}")
            
        finally:
            # Cleanup
            if self.work_dir.exists():
                shutil.rmtree(self.work_dir)

    async def _locate_source(self) -> Path:
        """Locates the source file. Handles local paths AND B2 downloads."""
        raw_path = self.media.file_path
        
        # 1. Local File (starts with /static)
        if raw_path.startswith("/static"):
             if "://" in raw_path:
                 raw_path = "/" + raw_path.split("/", 3)[-1]
             if raw_path.startswith("/"):
                 raw_path = raw_path[1:]
             full_path = Path(raw_path).resolve()
             if not full_path.exists():
                 # Try backend root relative
                 potential = Path(f"c:/vod-saas/vod-backend/{raw_path}")
                 if potential.exists():
                     return potential
                 # If local file missing, fail
                 raise FileNotFoundError(f"Local source missing: {full_path}")
             return full_path

        # 2. B2 File (Assume it's a key if not static)
        # Download to temp dir
        logger.info(f"Downloading from B2: {raw_path}")
        from modules.delivery.b2_service import get_b2_service
        b2 = get_b2_service()
        
        local_dl_path = self.work_dir / "source.mp4" # Assume mp4 or use extension from filename
        # Basic extension detection
        ext = os.path.splitext(self.media.filename)[1] or ".mp4"
        local_dl_path = self.work_dir / f"source{ext}"

        # Run blocking B2 download in threadpool
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, lambda: b2.download_file(raw_path, str(local_dl_path)))
        except Exception as e:
            logger.error(f"B2 Download Failed: {e}")
            raise e
            
        if not local_dl_path.exists():
            # Debug: Check directory contents
            files = list(self.work_dir.glob("*"))
            logger.error(f"Source file missing after download! Expected: {local_dl_path}. Found in dir: {files}")
            raise FileNotFoundError(f"Source file not found after download: {local_dl_path}")
            
        logger.info(f"Source downloaded successfully. Size: {local_dl_path.stat().st_size} bytes")
        return local_dl_path

    async def _transcode_hls(self, output_dir: Path):
        """
        Runs ffmpeg to generate HLS variants and master playlist.
        """
        # HLS Configuration
        # Variant 1: 720p (2500k)
        # Variant 2: 480p (1000k)
        
        # Ensure FFMPEG is available (simple check or assume in PATH)
        ffmpeg_cmd = "ffmpeg"
        
        # Output paths
        v1_dir = output_dir / "v1" # 720p
        
        # Command Construction (Simple usage for MVP)
        # We process separately or use complex filter_complex?
        v1_dir = output_dir / "v1"
        v1_dir.mkdir(parents=True, exist_ok=True)
        
        v2_dir = output_dir / "v2"
        v2_dir.mkdir(parents=True, exist_ok=True)
        
        ffmpeg_cmd = "ffmpeg"
        
        # Variant 1 (High)
        cmd1 = [
            ffmpeg_cmd, "-y", "-i", str(self.source_path),
            "-vf", "scale=-2:720", "-c:v", "libx264", "-b:v", "2500k", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "128k",
            "-hls_time", "6", "-hls_list_size", "0", "-f", "hls", 
            str(v1_dir / "playlist.m3u8")
        ]
        
        # Variant 2 (Mid)
        cmd2 = [
            ffmpeg_cmd, "-y", "-i", str(self.source_path),
            "-vf", "scale=-2:480", "-c:v", "libx264", "-b:v", "1000k", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "96k",
            "-hls_time", "6", "-hls_list_size", "0", "-f", "hls",
            str(v2_dir / "playlist.m3u8")
        ]
        
        # Run Transcodes
        await self._run_ffmpeg(cmd1)
        await self._run_ffmpeg(cmd2)
        
        # Create Master Playlist
        # Simple manual write
        master_playlist = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=2800000,RESOLUTION=1280x720
v1/playlist.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=1200000,RESOLUTION=854x480
v2/playlist.m3u8
"""
        with open(output_dir / "index.m3u8", "w") as f:
            f.write(master_playlist)
            
    async def _generate_thumbnail(self, output_path: Path):
        """Generates a poster image from the video."""
        cmd = [
            "ffmpeg", "-y", "-i", str(self.source_path),
            "-ss", "00:00:01.000", "-vframes", "1",
            str(output_path)
        ]
        try:
           await self._run_ffmpeg(cmd)
        except:
           # Retry at 0 if fails (e.g. video < 1s)
           cmd[3] = "00:00:00.000"
           await self._run_ffmpeg(cmd)

    async def _run_ffmpeg(self, cmd: list):
        import subprocess
        loop = asyncio.get_event_loop()
        
        def _exec():
             # Run blocking in thread
             return subprocess.run(cmd, capture_output=True)
             
        result = await loop.run_in_executor(None, _exec)
        
        if result.returncode != 0:
            stderr = result.stderr.decode('utf-8', errors='ignore')
            logger.error(f"FFMPEG Error: {stderr}")
            raise RuntimeError(f"FFMPEG failed with code {result.returncode}")

    async def _upload_results(self, hls_dir: Path, thumb_path: Path) -> str:
        """Moves processed files to permanent storage (Local or B2)."""
        
        original_key = self.media.file_path
        is_local = original_key.startswith("/static")
        
        if is_local:
             # Local Move Logic
             original_location = self.source_path.parent
             target_hls = original_location / "hls"
             if target_hls.exists():
                 shutil.rmtree(target_hls)
             shutil.copytree(hls_dir, target_hls)
             if thumb_path.exists():
                 shutil.copy2(thumb_path, original_location / "poster.jpg")
             
             parent = os.path.dirname(original_key)
             return f"{parent}/hls/index.m3u8"
        else:
            # B2 Upload Logic
            # Upload HLS files to `[original_folder]/hls/`
            # Original key: creators/uuid/videos/uuid/filename.mp4
            # Target prefix: creators/uuid/videos/uuid/hls/
            
            parent_key = os.path.dirname(original_key)
            hls_prefix = f"{parent_key}/hls"
            
            from modules.delivery.b2_service import get_b2_service
            b2 = get_b2_service()
            loop = asyncio.get_event_loop()
            
            # Upload recursive
            for root, dirs, files in os.walk(hls_dir):
                for file in files:
                    local_file = Path(root) / file
                    # Relative path for key structure
                    rel_path = local_file.relative_to(hls_dir)
                    # Use forward slashes for keys
                    key = f"{hls_prefix}/{rel_path}".replace("\\", "/")
                    
                    logger.info(f"Uploading B2: {key}")
                    await loop.run_in_executor(None, lambda: b2.upload_local_file(str(local_file), key))

            # Upload Thumbnail
            if thumb_path.exists():
                thumb_key = f"{parent_key}/poster.jpg"
                await loop.run_in_executor(None, lambda: b2.upload_local_file(str(thumb_path), thumb_key))
            
            # Return new key for Master Playlist
            return f"{hls_prefix}/index.m3u8"
