# -*- coding: utf-8 -*-
"""Minimal Extension Runtime for built-in action execution."""

from __future__ import annotations

import concurrent.futures
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from jsonschema import Draft202012Validator, exceptions as jsonschema_exceptions

from src.extensions.action_spec import (
    ActionContext,
    ActionResult,
    ExtensionErrorCode,
    ExtensionStatus,
)
from src.extensions.catalog import ExtensionCatalog
from src.extensions.concurrency import InMemoryConcurrencyGuard
from src.extensions.permissions import PermissionGuard
from src.extensions.run_envelope import input_hash, new_run_id

logger = logging.getLogger("dsa.extensions.runtime")


class ExtensionRuntime:
    """Executes ActionSpec handlers behind shared guards."""

    def __init__(
        self,
        catalog: Optional[ExtensionCatalog] = None,
        *,
        enabled: bool = True,
        max_call_depth: int = 3,
        permission_guard: Optional[PermissionGuard] = None,
        concurrency_guard: Optional[InMemoryConcurrencyGuard] = None,
        run_recorder=None,
    ):
        self.catalog = catalog or ExtensionCatalog()
        self.enabled = enabled
        self.max_call_depth = max_call_depth
        self.permission_guard = permission_guard or PermissionGuard()
        self.concurrency_guard = concurrency_guard or InMemoryConcurrencyGuard()
        self.run_recorder = run_recorder

    @classmethod
    def from_config(
        cls,
        config,
        catalog: Optional[ExtensionCatalog] = None,
        *,
        run_recorder=None,
    ) -> "ExtensionRuntime":
        """Create a runtime using Config-compatible extension settings."""
        return cls(
            catalog=catalog,
            enabled=getattr(config, "extensions_enabled", True),
            max_call_depth=getattr(config, "max_action_call_depth", 3),
            run_recorder=run_recorder,
        )

    def execute(
        self,
        action_id: str,
        input_payload: Optional[Dict[str, Any]] = None,
        *,
        caller: str = "system",
        context: Optional[ActionContext] = None,
    ) -> ActionResult:
        """Execute one action and return a structured result."""
        payload = input_payload if input_payload is not None else (context.input if context else {})
        run_id = context.run_id if context and context.run_id else new_run_id()
        created_at = datetime.now()

        if not self.enabled:
            return self._error_result(
                run_id,
                action_id,
                ExtensionStatus.UNAVAILABLE.value,
                ExtensionErrorCode.PLUGIN_DISABLED.value,
                created_at=created_at,
            )

        action = self.catalog.get(action_id)
        if action is None:
            return self._error_result(
                run_id,
                action_id,
                ExtensionStatus.UNAVAILABLE.value,
                ExtensionErrorCode.ACTION_NOT_FOUND.value,
                created_at=created_at,
            )

        action_context = context or ActionContext(action_id=action_id, input=payload, caller=caller)
        action_context.action_id = action_id
        action_context.input = payload
        if context is None or caller != "system":
            action_context.caller = caller or action_context.caller
        action_context.run_id = run_id
        action_context.input_hash = action_context.input_hash or input_hash(payload)
        if action.timeout_seconds and "timeout_seconds" not in action_context.budget:
            action_context.budget["timeout_seconds"] = action.timeout_seconds
        for key, value in action.budget_hints.items():
            action_context.budget_hints.setdefault(key, value)

        self._record_started(action, action_context, created_at)

        schema_error = self._validate_input(action, payload)
        if schema_error:
            error_code, diagnostics = schema_error
            result = self._error_result(
                run_id,
                action_id,
                ExtensionStatus.FAILED.value,
                error_code,
                diagnostics=diagnostics,
                created_at=created_at,
            )
            self._record_finished(result)
            return result

        if action_context.call_depth > self.max_call_depth:
            result = self._error_result(
                run_id,
                action_id,
                ExtensionStatus.FAILED.value,
                ExtensionErrorCode.CALL_DEPTH_EXCEEDED.value,
                created_at=created_at,
            )
            self._record_finished(result)
            return result

        denied = self.permission_guard.check(action, action_context)
        if denied:
            result = self._error_result(
                run_id,
                action_id,
                ExtensionStatus.FAILED.value,
                denied,
                created_at=created_at,
            )
            self._record_finished(result)
            return result

        if action.requires_confirmation:
            if not action_context.confirmation_id:
                result = self._error_result(
                    run_id,
                    action_id,
                    ExtensionStatus.FAILED.value,
                    ExtensionErrorCode.CONFIRMATION_REQUIRED.value,
                    created_at=created_at,
                )
                self._record_finished(result)
                return result

            from src.extensions.confirmations import get_confirmation_store

            if not get_confirmation_store().consume(
                action_context.confirmation_id,
                action_id=action_id,
                input_payload=payload,
            ):
                result = self._error_result(
                    run_id,
                    action_id,
                    ExtensionStatus.FAILED.value,
                    ExtensionErrorCode.CONFIRMATION_INVALID.value,
                    created_at=created_at,
                )
                self._record_finished(result)
                return result

        decision = self.concurrency_guard.acquire(action, action_context)
        if not decision.allowed:
            code = (
                ExtensionErrorCode.IDEMPOTENCY_CONFLICT.value
                if decision.reason == "duplicate"
                else ExtensionErrorCode.CONCURRENCY_LIMIT.value
            )
            result = self._error_result(
                run_id,
                action_id,
                ExtensionStatus.FAILED.value,
                code,
                diagnostics={"existing_run_id": decision.existing_run_id} if decision.existing_run_id else {},
                created_at=created_at,
            )
            self._record_finished(result)
            return result

        release_on_exit = True

        def _release_after_timeout(future) -> None:
            nonlocal release_on_exit
            release_on_exit = False
            future.add_done_callback(
                lambda _future: self.concurrency_guard.release(action, decision.dedupe_key)
            )

        try:
            result = self._call_handler(
                action.handler,
                action_context,
                action.timeout_seconds,
                on_running_timeout=_release_after_timeout,
            )
            if isinstance(result, ActionResult):
                result.run_id = run_id
                result.action_id = action_id
                result.created_at = created_at
                result.updated_at = max(result.updated_at, datetime.now())
                self._record_finished(result)
                return result
            action_result = ActionResult(
                run_id=run_id,
                action_id=action_id,
                status=ExtensionStatus.COMPLETED.value,
                result=result,
                created_at=created_at,
                updated_at=datetime.now(),
            )
            self._record_finished(action_result)
            return action_result
        except TimeoutError:
            result = self._error_result(
                run_id,
                action_id,
                ExtensionStatus.FAILED.value,
                ExtensionErrorCode.TIMEOUT.value,
                created_at=created_at,
            )
            self._record_finished(result)
            return result
        except Exception as exc:  # pragma: no cover - exact callers covered by tests
            logger.warning("Extension action failed: %s", action_id, exc_info=True)
            result = self._error_result(
                run_id,
                action_id,
                ExtensionStatus.FAILED.value,
                ExtensionErrorCode.INTERNAL.value,
                diagnostics={"error": str(exc)[:200]},
                created_at=created_at,
            )
            self._record_finished(result)
            return result
        finally:
            if release_on_exit:
                self.concurrency_guard.release(action, decision.dedupe_key)

    def _call_handler(
        self,
        handler,
        context: ActionContext,
        timeout_seconds: Optional[float],
        on_running_timeout=None,
    ) -> Any:
        if timeout_seconds is None or timeout_seconds <= 0:
            return handler(context)

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(handler, context)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            if not future.cancel() and on_running_timeout is not None:
                on_running_timeout(future)
            raise TimeoutError() from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _validate_input(self, action, payload: Any) -> Optional[tuple[str, Dict[str, Any]]]:
        """Validate action input with the declared JSON Schema."""
        if not isinstance(payload, dict):
            return (
                ExtensionErrorCode.INPUT_INVALID.value,
                {"reason": "Action input must be a JSON object."},
            )

        try:
            Draft202012Validator.check_schema(action.input_schema)
            Draft202012Validator(action.input_schema).validate(payload)
        except jsonschema_exceptions.ValidationError as exc:
            return (
                ExtensionErrorCode.INPUT_INVALID.value,
                {
                    "reason": exc.message,
                    "path": list(exc.path),
                    "schema_path": list(exc.schema_path),
                },
            )
        except jsonschema_exceptions.SchemaError as exc:
            return (
                ExtensionErrorCode.INTERNAL.value,
                {
                    "reason": f"Invalid action input schema: {exc.message}",
                    "schema_path": list(exc.schema_path),
                },
            )
        return None

    def _error_result(
        self,
        run_id: str,
        action_id: str,
        status: str,
        error_code: str,
        *,
        diagnostics: Optional[Dict[str, Any]] = None,
        created_at: Optional[datetime] = None,
    ) -> ActionResult:
        now = datetime.now()
        return ActionResult(
            run_id=run_id,
            action_id=action_id,
            status=status,
            error_code=error_code,
            diagnostics=diagnostics or {},
            created_at=created_at or now,
            updated_at=now,
        )

    def _record_started(self, action, context: ActionContext, created_at: datetime) -> None:
        if self.run_recorder is None:
            return
        try:
            self.run_recorder.create_run(
                {
                    "run_id": context.run_id,
                    "plugin_id": action.plugin_id,
                    "plugin_version": action.metadata.get("plugin_version", ""),
                    "action_id": action.id,
                    "caller": context.caller,
                    "trace_id": context.trace_id,
                    "traceparent": context.traceparent,
                    "input_hash": context.input_hash,
                    "idempotency_key": context.idempotency_key,
                    "status": ExtensionStatus.RUNNING.value,
                    "degraded": False,
                    "warnings": [],
                    "degradation": [],
                    "source_chain": [],
                    "source_errors": [],
                    "created_at": created_at,
                    "started_at": created_at,
                    "updated_at": created_at,
                }
            )
        except Exception as exc:  # pragma: no cover - fail-open defensive path
            logger.warning("Failed to record extension run start: %s", exc)

    def _record_finished(self, result: ActionResult) -> None:
        if self.run_recorder is None:
            return
        try:
            self.run_recorder.update_run(
                result.run_id,
                {
                    "status": result.status,
                    "degraded": bool(result.degradation),
                    "warnings": result.warnings,
                    "degradation": result.degradation,
                    "source_chain": result.source_chain,
                    "source_errors": result.source_errors,
                    "error_code": result.error_code,
                    "completed_at": result.updated_at,
                    "updated_at": result.updated_at,
                    "adapter_mode": self._adapter_mode(result.result),
                    "duration_ms": self._duration_ms(result),
                    "candidate_count": self._candidate_count(result.result),
                    "summary": self._summarize_result(result.result),
                },
            )
            if result.result is not None and hasattr(self.run_recorder, "save_result"):
                self.run_recorder.save_result(
                    result.run_id,
                    result.action_id,
                    result.result,
                    candidate_count=self._candidate_count(result.result),
                )
        except Exception as exc:  # pragma: no cover - fail-open defensive path
            logger.warning("Failed to record extension run finish: %s", exc)

    def _summarize_result(self, result: Any) -> str:
        if result is None:
            return ""
        if isinstance(result, dict):
            candidate_count = result.get("candidate_count")
            if candidate_count is not None:
                return f"{candidate_count} candidates"
            for key in ("summary", "message", "name"):
                value = result.get(key)
                if value:
                    return str(value)[:500]
        return str(result)[:500]

    def _adapter_mode(self, result: Any) -> str:
        if isinstance(result, dict):
            value = result.get("adapter_mode") or result.get("adapterMode")
            if value:
                return str(value)[:32]
        return ""

    def _duration_ms(self, result: ActionResult) -> int:
        return max(0, int((result.updated_at - result.created_at).total_seconds() * 1000))

    def _candidate_count(self, result: Any) -> int:
        if isinstance(result, dict):
            candidates = result.get("candidates")
            if isinstance(candidates, list):
                return len(candidates)
        if isinstance(result, list):
            return len(result)
        return 0
