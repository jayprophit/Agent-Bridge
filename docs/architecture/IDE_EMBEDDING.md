# IDE Embedding (v0.8, Part I)

The Bridge stays a bridge/plugin/runtime — not a proprietary IDE. Hosts
embed the Bridge panel and supply HostContext (workspace, open files,
selection, diagnostics) plus terminal/build/test events and diff/approval
UI (`ides/embedding.py`). Modes: STANDALONE, EMBEDDED_IDE_LEFT,
EMBEDDED_IDE_RIGHT, HEADLESS; sessions survive mode changes.
ReferenceIDEAdapter is interface-only shape (no vscode dependency); future
IDEs implement the same hooks. Core never imports host code.
