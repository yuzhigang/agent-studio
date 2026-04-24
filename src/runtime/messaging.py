# src/runtime/messaging.py
"""
Shared messaging contracts between runtime and worker layers.

SendResult lives here so that both runtime (outbox processor) and worker
(channels) can depend on it without creating runtime → worker coupling.
"""
from enum import Enum


class SendResult(Enum):
    SUCCESS = "success"
    RETRYABLE = "retryable"
    PERMANENT = "permanent"
