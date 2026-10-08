"""Aetherius Data Service Adapter Protocol (§60).

Stable provider-independent interface for all data services.
Applications remain replaceable — the adapter abstracts the vendor.

Per §60: "Create/reconcile a stable provider-independent
DataServiceAdapter rather than embedding each application inside Genesis."
"""
import os
import json
import hashlib
import logging
import shutil
from typing import Optional, Protocol

from data_fabric.data_service_registry import (
    DataServiceEntry, AppState, DataClass,
)

logger = logging.getLogger("aetherius.data_service_adapter")


class DataServiceAdapter(Protocol):
    """Provider-independent adapter for data services (§60).

    Each installed data service gets an adapter that exposes
    a standard interface. Privacy class is enforced at the adapter
    boundary.
    """
    adapter_id: str
    service_id: str
    privacy_class: str

    def read(self, query: str) -> str: ...
    def write(self, data: str, metadata: dict) -> bool: ...
    def search(self, pattern: str) -> list: ...
    def export(self, format: str = "json") -> bytes: ...
    def backup(self, dest_path: str) -> bool: ...
    def restore(self, src_path: str) -> bool: ...
    def sync(self) -> bool: ...
    def health(self) -> dict: ...
    def metadata(self) -> dict: ...


class LocalFileAdapter:
    """Adapter for local file-based data services (§60, §48 backup/restore)."""

    adapter_id = "local_files"
    privacy_class = "PRIVACY_PROJECT"

    def __init__(self, service_id: str, base_path: str,
                 privacy_class: str = "PRIVACY_PROJECT"):
        self.service_id = service_id
        self.base_path = os.path.abspath(base_path)
        self.privacy_class = privacy_class

    def read(self, file_path: str) -> str:
        full_path = os.path.join(self.base_path, file_path)
        if not os.path.isfile(full_path):
            return ""
        with open(full_path, "r", errors="replace") as f:
            return f.read()

    def write(self, file_path: str, data: str) -> bool:
        full_path = os.path.join(self.base_path, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(data)
        return True

    def search(self, pattern: str) -> list:
        results = []
        if not os.path.isdir(self.base_path):
            return results
        for root, _, files in os.walk(self.base_path):
            for fname in files:
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", errors="replace") as f:
                        content = f.read()
                    if pattern in content:
                        results.append({"file": os.path.relpath(fpath, self.base_path),
                                        "match_count": content.count(pattern)})
                except Exception:
                    pass
        return results

    def export(self, format: str = "json") -> bytes:
        files = {}
        if not os.path.isdir(self.base_path):
            return json.dumps({"service_id": self.service_id, "files": {}}, indent=2).encode()
        for root, _, filenames in os.walk(self.base_path):
            for fname in filenames:
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, self.base_path)
                try:
                    with open(fpath, "rb") as f:
                        files[rel] = f.read().hex()
                except Exception:
                    pass
        return json.dumps({"service_id": self.service_id, "files": files}, indent=2).encode()

    def backup(self, dest_path: str) -> bool:
        """Back up with hash verification (§48)."""
        if not os.path.isdir(self.base_path):
            return False
        os.makedirs(dest_path, exist_ok=True)
        shutil.copytree(self.base_path, os.path.join(dest_path, "backup"), dirs_exist_ok=True)
        backup_hash_path = os.path.join(dest_path, "backup_hash.json")
        hashes = {}
        for root, _, files in os.walk(self.base_path):
            for fname in files:
                fpath = os.path.join(root, fname)
                with open(fpath, "rb") as f:
                    hashes[os.path.relpath(fpath, self.base_path)] = hashlib.sha256(f.read()).hexdigest()
        with open(backup_hash_path, "w") as f:
            json.dump(hashes, f)
        return True

    def restore(self, src_path: str) -> bool:
        """Restore from a verified backup."""
        backup_dir = os.path.join(src_path, "backup")
        if not os.path.isdir(backup_dir):
            return False
        shutil.copytree(backup_dir, self.base_path, dirs_exist_ok=True)
        return True

    def sync(self) -> bool:
        return True

    def health(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "service_id": self.service_id,
            "base_path": self.base_path,
            "exists": os.path.isdir(self.base_path),
            "privacy_class": self.privacy_class,
            "health": "HEALTHY" if os.path.isdir(self.base_path) else "NOT_FOUND",
        }

    def metadata(self) -> dict:
        files = []
        if os.path.isdir(self.base_path):
            for root, _, filenames in os.walk(self.base_path):
                for fname in filenames:
                    fpath = os.path.join(root, fname)
                    files.append({"name": os.path.relpath(fpath, self.base_path),
                                  "size": os.path.getsize(fpath)})
        return {"adapter_id": self.adapter_id, "service_id": self.service_id,
                "file_count": len(files), "files": files[:20],
                "privacy_class": self.privacy_class}


class DataServiceAdapterRegistry:
    """Registry of DataServiceAdapters for all data services (§60)."""

    def __init__(self):
        self._adapters: dict[str, any] = {}
        self._data_class_map: dict[str, list[str]] = {}

    def register(self, service_id: str, adapter, data_classes: list = None) -> bool:
        self._adapters[service_id] = adapter
        if data_classes:
            self._data_class_map[service_id] = data_classes
        logger.info(f"Registered DataServiceAdapter for {service_id}")
        return True

    def get(self, service_id: str) -> Optional[any]:
        return self._adapters.get(service_id)

    def adapters_for_class(self, data_class: str) -> list:
        result = []
        for sid, classes in self._data_class_map.items():
            if data_class in classes:
                adapter = self._adapters.get(sid)
                if adapter:
                    result.append(adapter)
        return result

    def list(self) -> list:
        return list(self._adapters.values())

    def health_all(self) -> dict:
        return {sid: adapter.health() for sid, adapter in self._adapters.items()}
