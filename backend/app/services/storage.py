from pathlib import Path

from app.config import get_settings


class Storage:
    """Private object storage. `local` is for development only; production uses S3-compatible storage."""

    def __init__(self):
        s = get_settings()
        self.backend = s.storage_backend
        if self.backend == "s3":
            import boto3

            self.s3 = boto3.client("s3", endpoint_url=s.s3_endpoint_url or None)
            self.bucket = s.s3_bucket
        else:
            self.root = Path(s.storage_dir).resolve()
            self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not p.is_relative_to(self.root):
            raise ValueError("invalid storage key")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        if self.backend == "s3":
            self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        else:
            p = self._path(key)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)

    def get(self, key: str) -> bytes:
        if self.backend == "s3":
            return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        if self.backend == "s3":
            self.s3.delete_object(Bucket=self.bucket, Key=key)
        else:
            self._path(key).unlink(missing_ok=True)


_storage: Storage | None = None


def storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = Storage()
    return _storage
