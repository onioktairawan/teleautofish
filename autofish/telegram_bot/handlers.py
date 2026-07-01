from __future__ import annotations

def bind_runtime(namespace: dict):
    globals().update(namespace)

