# Restricted artifact storage

This directory is a repository placeholder, not a secure vault. Do not place
weights, embeddings, checkpoints, credentials, or other restricted artifacts
here. Store them in a private artifact service with encryption at rest,
managed keys, least-privilege access, and audit logging; provide access through
deployment-managed secrets.

The ignore rules help prevent accidental commits. They do not encrypt files or
protect data on the host. Git LFS is not an encryption mechanism.
