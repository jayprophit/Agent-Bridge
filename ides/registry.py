"""Independent registries for IDEs and workspaces."""
from __future__ import annotations

from typing import Iterable

from ides.descriptor import IDEScriptor, WorkspaceDescriptor


class IDERegistry:
    def __init__(self) -> None:
        self._ides: dict[str, IDEScriptor] = {}

    def register(self, descriptor: IDEScriptor, replace: bool = False) -> None:
        if descriptor.ide_id in self._ides and not replace:
            raise ValueError(f"duplicate ide_id: {descriptor.ide_id}")
        self._ides[descriptor.ide_id] = descriptor

    def get(self, ide_id: str) -> IDEScriptor:
        try:
            return self._ides[ide_id]
        except KeyError:
            raise KeyError(f"unknown IDE: {ide_id!r}")

    def ids(self) -> list[str]:
        return sorted(self._ides)

    def list(self, ide_type: str = "", status: str = "",
             protocol: str = "", capability: str = "") -> list[IDEScriptor]:
        result = []
        for ide in self._ides.values():
            if ide_type and ide.ide_type != ide_type:
                continue
            if status and ide.status != status:
                continue
            if protocol and protocol not in ide.protocols:
                continue
            if capability and capability not in ide.capabilities:
                continue
            result.append(ide)
        return sorted(result, key=lambda item: item.ide_id)

    def search(self, query: str, limit: int = 20) -> list[IDEScriptor]:
        words = [word.lower() for word in query.split() if word]
        scored = []
        for ide in self._ides.values():
            haystack = " ".join((
                ide.ide_id, ide.name, ide.vendor, ide.description
                if hasattr(ide, "description") else "",
                ide.ide_type, " ".join(ide.capabilities),
                " ".join(ide.protocols),
            )).lower()
            score = sum(2 for word in words if word in haystack)
            if score:
                scored.append((score, ide))
        scored.sort(key=lambda item: (-item[0], item[1].ide_id))
        return [ide for _, ide in scored[:limit]]

    def describe(self, ide_id: str) -> dict:
        return self.get(ide_id).to_dict()

    def __len__(self) -> int:
        return len(self._ides)


class WorkspaceRegistry:
    def __init__(self) -> None:
        self._workspaces: dict[str, WorkspaceDescriptor] = {}

    def register(self, descriptor: WorkspaceDescriptor,
                 replace: bool = False) -> None:
        if descriptor.workspace_id in self._workspaces and not replace:
            raise ValueError(f"duplicate workspace_id: {descriptor.workspace_id}")
        self._workspaces[descriptor.workspace_id] = descriptor

    def get(self, workspace_id: str) -> WorkspaceDescriptor:
        try:
            return self._workspaces[workspace_id]
        except KeyError:
            raise KeyError(f"unknown workspace: {workspace_id!r}")

    def list(self, ide_id: str = "", node_id: str = "",
             project_type: str = "") -> list[WorkspaceDescriptor]:
        result = []
        for workspace in self._workspaces.values():
            if ide_id and ide_id not in workspace.associated_ides:
                continue
            if node_id and workspace.node_id != node_id:
                continue
            if project_type and workspace.project_type != project_type:
                continue
            result.append(workspace)
        return sorted(result, key=lambda item: item.workspace_id)

    def attach_ide(self, workspace_id: str, ide_id: str) -> None:
        workspace = self.get(workspace_id)
        if ide_id not in workspace.associated_ides:
            workspace.associated_ides.append(ide_id)

    def __len__(self) -> int:
        return len(self._workspaces)
