"""Credential storage boundary. Callers only ever hold an auth_ref (UUID).
Prototype backend: Fernet-encrypted rows in PostgreSQL. Production: implement the same
interface against AWS Secrets Manager / GCP Secret Manager / Vault."""
import json
import uuid
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.core.security import decrypt, encrypt
from app.db.base import utcnow
from app.db.models import CredentialSecret


class SecretStore(ABC):
    @abstractmethod
    def put(self, tenant_id: uuid.UUID, kind: str, payload: dict) -> uuid.UUID: ...

    @abstractmethod
    def get(self, tenant_id: uuid.UUID, ref: uuid.UUID) -> dict: ...

    @abstractmethod
    def update(self, tenant_id: uuid.UUID, ref: uuid.UUID, payload: dict) -> None: ...

    @abstractmethod
    def delete(self, tenant_id: uuid.UUID, ref: uuid.UUID) -> None: ...


class DbEncryptedSecretStore(SecretStore):
    def __init__(self, db: Session):
        self.db = db

    def _load(self, tenant_id, ref) -> CredentialSecret:
        row = self.db.get(CredentialSecret, ref)
        if row is None or row.tenant_id != tenant_id:
            raise KeyError("credential not found")
        return row

    def put(self, tenant_id, kind, payload):
        row = CredentialSecret(tenant_id=tenant_id, kind=kind, ciphertext=encrypt(json.dumps(payload)))
        self.db.add(row)
        self.db.flush()
        return row.id

    def get(self, tenant_id, ref):
        return json.loads(decrypt(self._load(tenant_id, ref).ciphertext))

    def update(self, tenant_id, ref, payload):
        row = self._load(tenant_id, ref)
        row.ciphertext = encrypt(json.dumps(payload))
        row.rotated_at = utcnow()
        self.db.flush()

    def delete(self, tenant_id, ref):
        self.db.delete(self._load(tenant_id, ref))
        self.db.flush()


def get_secret_store(db: Session) -> SecretStore:
    return DbEncryptedSecretStore(db)
