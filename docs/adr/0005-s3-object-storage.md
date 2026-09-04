# ADR 0005: S3-compatible object storage

Status: accepted.

Store only media metadata in PostgreSQL. Generated S3 keys, presigned uploads, validation, and signed
downloads avoid database BLOB cost and allow AWS S3, MinIO, SeaweedFS, or compatible providers. The
adapter boundary permits later malware quarantine/scanning and CDN delivery.

Use separate internal and public endpoint configuration for one logical S3 service. The internal
endpoint is used for trusted backend operations. A public-endpoint client generates browser upload
and download signatures. This is intentionally two clients rather than string replacement: SigV4
binds the request Host, so rewriting an internally signed URL can invalidate the signature. Both
clients use the same bucket, region, access key, and secret. Production requires an HTTPS public
endpoint.
