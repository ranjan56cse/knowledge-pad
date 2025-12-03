"""
Cloudflare R2 Storage Implementation
S3-compatible object storage for PDF files
"""
import boto3
import os
from dotenv import load_dotenv

load_dotenv()

class CloudflareR2Storage:
    def __init__(self):
        """Initialize Cloudflare R2 client"""
        account_id = os.getenv('CLOUDFLARE_ACCOUNT_ID')
        access_key = os.getenv('R2_ACCESS_KEY_ID')
        secret_key = os.getenv('R2_SECRET_ACCESS_KEY')
        
        if not all([account_id, access_key, secret_key]):
            print("⚠️  Warning: R2 credentials not fully configured")
            print("   Set CLOUDFLARE_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY in .env")
        
        self.s3_client = boto3.client(
            's3',
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name='auto'  # R2 uses 'auto'
        )
        self.bucket_name = 'knowledge-pad-pdfs'
        print("✓ R2 storage initialized")
    
    def upload_pdf(self, file_path, object_name=None):
        """
        Upload PDF to R2
        
        Args:
            file_path: Path to local PDF file
            object_name: S3 object name (if None, uses file_path basename)
        
        Returns:
            bool: True if successful
        """
        if object_name is None:
            object_name = os.path.basename(file_path)
        
        try:
            self.s3_client.upload_file(
                file_path, 
                self.bucket_name, 
                object_name,
                ExtraArgs={'ContentType': 'application/pdf'}
            )
            print(f"✓ Uploaded: {object_name}")
            return True
        except Exception as e:
            print(f"✗ Upload failed: {e}")
            return False
    
    def download_pdf(self, object_name, download_path):
        """Download PDF from R2"""
        try:
            self.s3_client.download_file(
                self.bucket_name,
                object_name,
                download_path
            )
            print(f"✓ Downloaded: {object_name}")
            return True
        except Exception as e:
            print(f"✗ Download failed: {e}")
            return False
    
    def get_pdf_url(self, object_name, expires_in=3600):
        """Generate presigned URL for PDF access"""
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': object_name
                },
                ExpiresIn=expires_in
            )
            return url
        except Exception as e:
            print(f"✗ URL generation failed: {e}")
            return None
    
    def list_pdfs(self):
        """List all PDFs in bucket"""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name
            )
            if 'Contents' in response:
                return [obj['Key'] for obj in response['Contents']]
            return []
        except Exception as e:
            print(f"✗ List failed: {e}")
            return []
    
    def delete_pdf(self, object_name):
        """Delete PDF from R2"""
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=object_name
            )
            print(f"✓ Deleted: {object_name}")
            return True
        except Exception as e:
            print(f"✗ Delete failed: {e}")
            return False
