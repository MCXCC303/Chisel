from __future__ import annotations

import hashlib

_CONTRIBUTOR_SALT = "755032f070efc5950d891576fea943e2"
_CONTRIBUTOR_HASH = "631a6b319b387ec6bc48db2a88fb462a66b6a6a4fa9de8ae0b9b0060504851c9"

def verify_password(password: str) -> bool:
	h = hashlib.sha256((_CONTRIBUTOR_SALT + password).encode("utf-8")).hexdigest()
	return h == _CONTRIBUTOR_HASH
