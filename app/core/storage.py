import os
import shutil
from fastapi import UploadFile
from uuid import uuid4
from pathlib import Path

# MVP: Local Storage in 'static/uploads'
UPLOAD_DIR = Path("static/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

class LocalStorage:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    async def save_upload(self, file: UploadFile, creator_id: str) -> dict:
        """
        Saves uploaded file to disk.
        Returns dict with file_path, size, filename.
        """
        # Create user specific folder or just flat?
        # Let's use date-based or random to avoid collision
        file_ext = Path(file.filename).suffix
        safe_filename = f"{uuid4()}{file_ext}"
        
        # Determine subdir (e.g. video vs image?)
        # For now flat
        destination = self.base_dir / safe_filename
        
        # Async writing
        # UploadFile.read() is async? methods are async waitable.
        # But saving to disk is usually blocking IO unless using aiofiles.
        # For MVP, shutil.copyfileobj is synchronous but fast enough for small concurrency.
        # Ideally run in threadpool.
        
        try:
            file.file.seek(0)
            with destination.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        finally:
            file.file.close()

        # Get size
        size = destination.stat().st_size
        
        return {
            "path": str(destination).replace("\\", "/"), # Normalize path separators
            "filename": file.filename,
            "size": size,
            "url": f"/static/uploads/{safe_filename}"
        }

storage = LocalStorage(UPLOAD_DIR)
