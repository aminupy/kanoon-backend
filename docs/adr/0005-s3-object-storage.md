# ADR 0005: S3-compatible object storage

Status: accepted.

Store only media metadata in PostgreSQL. Generated S3 keys, presigned uploads, validation, and signed
downloads avoid database BLOB cost and allow AWS S3, MinIO, SeaweedFS, or compatible providers. The
adapter boundary permits later malware quarantine/scanning and CDN delivery.

