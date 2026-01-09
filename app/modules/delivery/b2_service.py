from b2sdk.v2 import InMemoryAccountInfo, B2Api
from functools import lru_cache
from app.core.config import settings

class B2Service:

    def __init__(self):
        self.info = InMemoryAccountInfo()
        self.b2_api = B2Api(self.info)
        self.application_key_id = settings.B2_APPLICATION_KEY_ID
        self.application_key = settings.B2_APPLICATION_KEY
        self.bucket_name = settings.B2_BUCKET_NAME
        
        self.bucket = None
        self.is_mock = False
        
        if self.application_key_id and self.application_key and self.bucket_name:
            try:
                self.b2_api.authorize_account("production", self.application_key_id, self.application_key)
                self.bucket = self.b2_api.get_bucket_by_name(self.bucket_name)
                self.ensure_cors_rules()
            except Exception as e:
                print(f"B2 Init Failed, falling back to mock: {e}")
                self.is_mock = True
        else:
            print("B2 credentials missing, using Mock Mode.")
            self.is_mock = True

    def ensure_cors_rules(self):
        """
        Ensures the bucket allows CORS for direct browser uploads.
        """
        if not self.bucket:
            return
            
        try:
            # Check existing rules to avoid redundant updates?
            # For simplicity, we just enforce the needed rule for the MVP.
            # We need to allow b2_upload_file, b2_upload_part, and downloads.
            
            cors_rules = [
                {
                    "corsRuleName": "allowAny",
                    "allowedOrigins": ["*"],
                    "allowedHeaders": ["*"],
                    "allowedOperations": [
                        "b2_download_file_by_id",
                        "b2_download_file_by_name", 
                        "b2_upload_file",
                        "b2_upload_part"
                    ],
                    "maxAgeSeconds": 3600
                }
            ]
            
            # Use b2sdk update method
            # Note: b2sdk v1/v2 might differ. 
            # In v2, bucket.update(cors_rules=...)
            
            self.bucket.update(cors_rules=cors_rules)
            print(f"B2 CORS rules updated for bucket: {self.bucket_name}")
            
        except Exception as e:
            print(f"Failed to update B2 CORS rules: {e}")
            print("Ensure your Application Key has 'writeBucket' permissions.")

    def get_upload_url(self):
        """
        Returns (upload_url, auth_token) for the bucket.
        """
        if self.is_mock:
            # Return local mock endpoint
            # In comp, this would be the actual server address
            return "http://localhost:8000/api/v1/cms/b2-mock-upload", "mock-token"

        if not self.bucket:
             raise ValueError("B2 Bucket not initialized and Mock Mode failed.")
             
        # b2sdk v2: Use session to get upload URL explicitly
        # bucket.id_ is the ID string
        response = self.b2_api.session.get_upload_url(bucket_id=self.bucket.id_)
        return response['uploadUrl'], response['authorizationToken']

    def get_download_url(self, file_key: str):
        """
        Generates a secure download URL.
        If mock, returns local URL.
        If B2, returns signed URL (valid for 24h).
        """
        print(f"[DEBUG] Generating Download URL for key: {file_key}")
        if self.is_mock:
             # Just stripping conventions for mock
             return f"http://localhost:8000/static/uploads/{file_key}"

        if not self.bucket:
             return None
             
        try:
            # Generate generic download token
            # Note: In production, one might cache this or generate specific tokens per file
            # For this MVP, we generate a token valid for the specific file prefix or bucket
            # b2sdk v2: bucket.get_download_authorization
            
            # B2 Authorization Logic
            valid_duration = 86400 # 24h
            
            # If HLS Manifest, authorize the entire parent folder (so segments work)
            if file_key.endswith(".m3u8"):
                 # file_key: creators/uid/videos/vid/hls/index.m3u8
                 # prefix: creators/uid/videos/vid/hls/
                 # Note: B2 prefix includes all files starting with this string.
                 prefix = file_key.rsplit('/', 1)[0] + '/'
            else:
                 # Exact match for single files
                 prefix = file_key
            
            auth_token = self.bucket.get_download_authorization(
                file_name_prefix=prefix, 
                valid_duration_in_seconds=valid_duration
            )
            
            # Base download URL
            download_url = self.b2_api.account_info.get_download_url()
            bucket_name = self.bucket_name
            
            return f"{download_url}/file/{bucket_name}/{file_key}?Authorization={auth_token}"
            
        except Exception as e:
            print(f"Error generating B2 download URL: {e}")
        except Exception as e:
            print(f"Error generating B2 download URL: {e}")
            return None

    def upload_file(self, file_data: bytes, file_key: str):
        """
        Uploads bytes to B2 (or Mock storage).
        """
        if self.is_mock:
            # Mock: Save to static/uploads/{file_key}
            # file_key might contain slashes "creators/uid/kyc/img.jpg"
            import pathlib
            
            # Remove "creators/" prefix from mock to keep it clean or keep it? 
            # Let's keep structure but inside static/uploads
            base_path = pathlib.Path("static/uploads")
            full_path = base_path / file_key
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(full_path, "wb") as f:
                f.write(file_data)
            
            return f"/static/uploads/{file_key}"

        if not self.bucket:
             raise ValueError("B2 Bucket not initialized")
             
        try:
            # Upload to B2
            # info returns FileVersionInfo
            uploaded_file = self.bucket.upload_bytes(file_data, file_key)
            # We don't return the B2 ID generally unless needed. 
            # We return the KEY (path) which we already know, or the public/presigned URL?
            # For consistency with get_download_url logic, we just return the key.
            return file_key
        except Exception as e:
            print(f"B2 Upload Failed: {e}")
            raise e

    def upload_local_file(self, local_path: str, file_key: str):
        """
        Uploads a local file to B2 (or Mock) efficiently.
        """
        if self.is_mock:
             import shutil
             import pathlib
             base_path = pathlib.Path("static/uploads")
             full_path = base_path / file_key
             full_path.parent.mkdir(parents=True, exist_ok=True)
             shutil.copy2(local_path, str(full_path))
             return f"/static/uploads/{file_key}"
             
        if not self.bucket:
             raise ValueError("B2 Bucket not initialized")
             
        try:
             self.bucket.upload_local_file(local_file=local_path, file_name=file_key)
             return file_key
        except Exception as e:
             print(f"B2 Upload Local Failed: {e}")
             raise e

    def download_file(self, file_key: str, dest_path: str):
        """
        Downloads a file from B2 (or Mock) to a local path.
        """
        if self.is_mock:
            # Mock: Copy from static/uploads/{file_key}
            import shutil
            import pathlib
            base_path = pathlib.Path("static/uploads")
            full_path = base_path / file_key
            
            if not full_path.exists():
                raise FileNotFoundError(f"Mock file not found: {full_path}")
                
            shutil.copy2(str(full_path), dest_path)
            return

        if not self.bucket:
             raise ValueError("B2 Bucket not initialized")
             
        try:
            print(f"[DEBUG B2] Downloading {file_key} to {dest_path}")
            
            # b2sdk v2: download_file_by_name returns a DownloadedFile object
            downloaded = self.bucket.download_file_by_name(file_key)
            with open(dest_path, 'wb') as f:
                downloaded.save(f)

            import os
            if os.path.exists(dest_path):
                size = os.path.getsize(dest_path)
                print(f"[DEBUG B2] File downloaded check passed. Size: {size}")
                if size == 0:
                     print("[DEBUG B2] WARNING: Downloaded file is 0 bytes.")
            else:
                print(f"[DEBUG B2] ERROR: download_file_by_name finished but file missing at {dest_path}")
                
        except Exception as e:
            print(f"B2 Download Failed: {e}")
            raise e

@lru_cache()
def get_b2_service():
    return B2Service()
