# -*- coding: utf-8 -*-
"""Tests for the Extension Runtime MVP."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from src.extensions import (
    ActionContext,
    ActionResult,
    ActionSpec,
    ExtensionCatalog,
    ExtensionErrorCode,
    ExtensionRuntime,
    ExtensionStatus,
)
from src.extensions.manifests import PluginManifest
from src.extensions.run_envelope import input_hash, new_run_id
from src.extensions.security import redact_sensitive_mapping


def _echo_action(**overrides):
    def _handler(context: ActionContext):
        return {"echo": context.input, "caller": context.caller}

    payload = {
        "id": "test.echo",
        "plugin_id": "test",
        "name": "Echo",
        "description": "Echo input",
        "category": "action",
        "mode": "sync",
        "input_schema": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
            "additionalProperties": False,
        },
        "handler": _handler,
    }
    payload.update(overrides)
    return ActionSpec(**payload)


def test_catalog_registers_and_lists_actions():
    catalog = ExtensionCatalog()
    action = _echo_action()

    catalog.register(action)

    assert len(catalog) == 1
    assert "test.echo" in catalog
    assert catalog.get("test.echo") == action
    assert catalog.list_actions(plugin_id="test") == [action]


def test_catalog_rejects_duplicate_action_ids():
    catalog = ExtensionCatalog([_echo_action()])

    with pytest.raises(ValueError, match="Action already registered"):
        catalog.register(_echo_action())


def test_action_spec_validation_rejects_bad_values():
    action = _echo_action(mode="stream")

    with pytest.raises(ValueError, match="Unsupported action mode"):
        action.validate()


def test_runtime_execute_success():
    runtime = ExtensionRuntime(ExtensionCatalog([_echo_action()]))

    result = runtime.execute("test.echo", {"message": "hello"}, caller="web")

    assert result.status == ExtensionStatus.COMPLETED.value
    assert result.action_id == "test.echo"
    assert result.run_id.startswith("run_")
    assert result.result == {"echo": {"message": "hello"}, "caller": "web"}
    assert result.error_code is None


def test_runtime_validates_action_input_schema_before_handler():
    called = {"value": False}

    def _handler(_context: ActionContext):
        called["value"] = True
        return {"unexpected": True}

    action = _echo_action(handler=_handler)
    runtime = ExtensionRuntime(ExtensionCatalog([action]))

    result = runtime.execute("test.echo", {"message": 123, "extra": "nope"}, caller="web")

    assert result.status == ExtensionStatus.FAILED.value
    assert result.error_code == ExtensionErrorCode.INPUT_INVALID.value
    assert "reason" in result.diagnostics
    assert called["value"] is False


def test_runtime_records_started_and_finished_run_metadata():
    class Recorder:
        def __init__(self):
            self.created = []
            self.updated = []

        def create_run(self, fields):
            self.created.append(fields)

        def update_run(self, run_id, fields):
            self.updated.append((run_id, fields))

    recorder = Recorder()
    action = _echo_action(metadata={"plugin_version": "0.1.0"})
    runtime = ExtensionRuntime(ExtensionCatalog([action]), run_recorder=recorder)

    result = runtime.execute("test.echo", {"message": "hello"}, caller="web")

    assert result.status == ExtensionStatus.COMPLETED.value
    assert recorder.created[0]["run_id"] == result.run_id
    assert recorder.created[0]["plugin_id"] == "test"
    assert recorder.created[0]["plugin_version"] == "0.1.0"
    assert recorder.created[0]["status"] == ExtensionStatus.RUNNING.value
    assert recorder.updated[0][0] == result.run_id
    assert recorder.updated[0][1]["status"] == ExtensionStatus.COMPLETED.value
    assert recorder.updated[0][1]["summary"] == str(result.result)[:500]
    assert isinstance(recorder.updated[0][1]["duration_ms"], int)


def test_runtime_records_adapter_mode_and_candidate_summary():
    class Recorder:
        def __init__(self):
            self.updated = []

        def create_run(self, _fields):
            pass

        def update_run(self, run_id, fields):
            self.updated.append((run_id, fields))

        def save_result(self, *_args, **_kwargs):
            pass

    def _handler(_context: ActionContext):
        return {"adapter_mode": "python", "candidate_count": 2, "candidates": [{}, {}]}

    runtime = ExtensionRuntime(
        ExtensionCatalog([_echo_action(handler=_handler)]),
        run_recorder=Recorder(),
    )

    result = runtime.execute("test.echo", {"message": "hello"}, caller="web")

    assert result.status == ExtensionStatus.COMPLETED.value
    assert runtime.run_recorder.updated[0][1]["adapter_mode"] == "python"
    assert runtime.run_recorder.updated[0][1]["candidate_count"] == 2
    assert runtime.run_recorder.updated[0][1]["summary"] == "2 candidates"


def test_runtime_normalizes_action_result_timestamps_for_duration():
    class Recorder:
        def __init__(self):
            self.updated = []

        def create_run(self, _fields):
            pass

        def update_run(self, run_id, fields):
            self.updated.append((run_id, fields))

    def _handler(context: ActionContext):
        time.sleep(0.01)
        return ActionResult(
            run_id=context.run_id,
            action_id=context.action_id,
            status=ExtensionStatus.COMPLETED.value,
            result={"ok": True},
        )

    recorder = Recorder()
    action = _echo_action(handler=_handler)
    runtime = ExtensionRuntime(ExtensionCatalog([action]), run_recorder=recorder)

    result = runtime.execute("test.echo", {"message": "hello"}, caller="web")

    assert result.status == ExtensionStatus.COMPLETED.value
    assert recorder.updated[0][1]["duration_ms"] >= 1


def test_runtime_preserves_context_caller_when_caller_not_overridden():
    runtime = ExtensionRuntime(ExtensionCatalog([_echo_action()]))
    context = ActionContext(action_id="test.echo", input={"message": "hi"}, caller="agent")

    result = runtime.execute("test.echo", {"message": "hi"}, context=context)

    assert result.result["caller"] == "agent"


def test_runtime_disabled_returns_structured_error():
    runtime = ExtensionRuntime(ExtensionCatalog([_echo_action()]), enabled=False)

    result = runtime.execute("test.echo", {"message": "hello"})

    assert result.status == ExtensionStatus.UNAVAILABLE.value
    assert result.error_code == ExtensionErrorCode.PLUGIN_DISABLED.value


def test_runtime_missing_action_returns_structured_error():
    runtime = ExtensionRuntime(ExtensionCatalog())

    result = runtime.execute("missing.action", {})

    assert result.status == ExtensionStatus.UNAVAILABLE.value
    assert result.error_code == ExtensionErrorCode.ACTION_NOT_FOUND.value


def test_runtime_blocks_unsupported_caller():
    action = _echo_action(supported_callers=["web"])
    runtime = ExtensionRuntime(ExtensionCatalog([action]))

    result = runtime.execute("test.echo", {"message": "hello"}, caller="agent")

    assert result.status == ExtensionStatus.FAILED.value
    assert result.error_code == ExtensionErrorCode.CALLER_NOT_ALLOWED.value


def test_runtime_requires_confirmation_when_declared():
    action = _echo_action(requires_confirmation=True)
    runtime = ExtensionRuntime(ExtensionCatalog([action]))

    result = runtime.execute("test.echo", {"message": "hello"})

    assert result.status == ExtensionStatus.FAILED.value
    assert result.error_code == ExtensionErrorCode.CONFIRMATION_REQUIRED.value


def test_runtime_rejects_invalid_confirmation_token():
    action = _echo_action(requires_confirmation=True)
    runtime = ExtensionRuntime(ExtensionCatalog([action]))
    context = ActionContext(
        action_id="test.echo",
        input={"message": "hello"},
        confirmation_id="cnf_not_real",
    )

    result = runtime.execute("test.echo", {"message": "hello"}, context=context)

    assert result.status == ExtensionStatus.FAILED.value
    assert result.error_code == ExtensionErrorCode.CONFIRMATION_INVALID.value


def test_runtime_consumes_matching_confirmation_token_once():
    from src.extensions.confirmations import get_confirmation_store

    payload = {"message": "hello"}
    token = get_confirmation_store().issue(
        action_id="test.echo",
        scope="test.scope",
        input_payload=payload,
    )
    action = _echo_action(requires_confirmation=True)
    runtime = ExtensionRuntime(ExtensionCatalog([action]))
    context = ActionContext(
        action_id="test.echo",
        input=payload,
        confirmation_id=token.confirmation_id,
    )

    first = runtime.execute("test.echo", payload, context=context)
    second = runtime.execute(
        "test.echo",
        payload,
        context=ActionContext(
            action_id="test.echo",
            input=payload,
            confirmation_id=token.confirmation_id,
        ),
    )

    assert first.status == ExtensionStatus.COMPLETED.value
    assert second.status == ExtensionStatus.FAILED.value
    assert second.error_code == ExtensionErrorCode.CONFIRMATION_INVALID.value


def test_runtime_blocks_excessive_call_depth():
    runtime = ExtensionRuntime(ExtensionCatalog([_echo_action()]), max_call_depth=1)
    context = ActionContext(action_id="test.echo", input={"message": "hello"}, call_depth=2)

    result = runtime.execute("test.echo", {"message": "hello"}, context=context)

    assert result.status == ExtensionStatus.FAILED.value
    assert result.error_code == ExtensionErrorCode.CALL_DEPTH_EXCEEDED.value


def test_runtime_handles_handler_exception():
    def _handler(_context: ActionContext):
        raise RuntimeError("boom")

    action = _echo_action(handler=_handler)
    runtime = ExtensionRuntime(ExtensionCatalog([action]))

    result = runtime.execute("test.echo", {"message": "hello"})

    assert result.status == ExtensionStatus.FAILED.value
    assert result.error_code == ExtensionErrorCode.INTERNAL.value
    assert result.diagnostics["error"] == "boom"


def test_runtime_timeout_returns_structured_error():
    def _handler(_context: ActionContext):
        time.sleep(0.2)
        return {"late": True}

    action = _echo_action(handler=_handler, timeout_seconds=0.01)
    runtime = ExtensionRuntime(ExtensionCatalog([action]))

    result = runtime.execute("test.echo", {"message": "hello"})

    assert result.status == ExtensionStatus.FAILED.value
    assert result.error_code == ExtensionErrorCode.TIMEOUT.value


def test_runtime_keeps_dedupe_slot_until_timed_out_handler_finishes():
    started = threading.Event()
    finish = threading.Event()

    def _handler(_context: ActionContext):
        started.set()
        finish.wait(timeout=1)
        return {"late": True}

    action = _echo_action(handler=_handler, timeout_seconds=0.01)
    runtime = ExtensionRuntime(ExtensionCatalog([action]))
    context = ActionContext(
        action_id="test.echo",
        input={"message": "hello"},
        idempotency_key="same-request",
    )

    first = runtime.execute("test.echo", {"message": "hello"}, context=context)
    assert started.is_set()

    try:
        retry = runtime.execute(
            "test.echo",
            {"message": "hello"},
            context=ActionContext(
                action_id="test.echo",
                input={"message": "hello"},
                idempotency_key="same-request",
            ),
        )

        assert first.status == ExtensionStatus.FAILED.value
        assert first.error_code == ExtensionErrorCode.TIMEOUT.value
        assert retry.status == ExtensionStatus.FAILED.value
        assert retry.error_code == ExtensionErrorCode.IDEMPOTENCY_CONFLICT.value
    finally:
        finish.set()


def test_runtime_applies_action_budget_hints_to_context_defaults():
    observed = []

    def _handler(context: ActionContext):
        observed.append(dict(context.budget_hints))
        return {"ok": True}

    action = _echo_action(
        handler=_handler,
        budget_hints={"max_items": 5, "max_tokens": 100},
    )
    runtime = ExtensionRuntime(ExtensionCatalog([action]))
    context = ActionContext(
        action_id="test.echo",
        input={"message": "hello"},
        budget_hints={"max_items": 2},
    )

    result = runtime.execute("test.echo", {"message": "hello"}, context=context)

    assert result.status == ExtensionStatus.COMPLETED.value
    assert observed == [{"max_items": 2, "max_tokens": 100}]


def test_runtime_idempotency_key_dedupe_conflict():
    gate = {"entered": False}

    def _handler(_context: ActionContext):
        if not gate["entered"]:
            gate["entered"] = True
            nested = runtime.execute(
                "test.echo",
                {"message": "hello"},
                context=ActionContext(
                    action_id="test.echo",
                    input={"message": "hello"},
                    idempotency_key="same-request",
                ),
            )
            return {"nested_error": nested.error_code}
        return {"unexpected": True}

    action = _echo_action(handler=_handler, dedupe_strategy="input_hash")
    runtime = ExtensionRuntime(ExtensionCatalog([action]))
    context = ActionContext(
        action_id="test.echo",
        input={"message": "hello"},
        idempotency_key="same-request",
    )

    result = runtime.execute("test.echo", {"message": "hello"}, context=context)

    assert result.status == ExtensionStatus.COMPLETED.value
    assert result.result["nested_error"] == ExtensionErrorCode.IDEMPOTENCY_CONFLICT.value


def test_runtime_concurrency_limit_blocks_reentrant_action_without_dedupe():
    gate = {"entered": False}

    def _handler(_context: ActionContext):
        if not gate["entered"]:
            gate["entered"] = True
            nested = runtime.execute("test.echo", {"message": "hello"})
            return {"nested_error": nested.error_code}
        return {"unexpected": True}

    action = _echo_action(handler=_handler, dedupe_strategy="none", concurrency_limit=1)
    runtime = ExtensionRuntime(ExtensionCatalog([action]))

    result = runtime.execute("test.echo", {"message": "hello"})

    assert result.status == ExtensionStatus.COMPLETED.value
    assert result.result["nested_error"] == ExtensionErrorCode.CONCURRENCY_LIMIT.value


def test_runtime_from_config_uses_extension_settings():
    config = SimpleNamespace(extensions_enabled=False, max_action_call_depth=7)

    runtime = ExtensionRuntime.from_config(config, ExtensionCatalog([_echo_action()]))

    assert runtime.enabled is False
    assert runtime.max_call_depth == 7


def test_input_hash_is_stable_for_key_order():
    assert input_hash({"b": 2, "a": 1}) == input_hash({"a": 1, "b": 2})


def test_new_run_id_uses_run_prefix():
    assert new_run_id().startswith("run_")


def test_manifest_from_dict_validates_required_fields():
    manifest = PluginManifest.from_dict(
        {
            "id": "demo",
            "name": "Demo",
            "version": "0.1.0",
            "kind": "builtin",
            "supported_markets": ["cn"],
        }
    )

    assert manifest.id == "demo"
    assert manifest.supported_markets == ["cn"]


def test_redact_sensitive_mapping_masks_known_secret_keys():
    redacted = redact_sensitive_mapping(
        {
            "api_key": "abc",
            "token": "def",
            "normal": "value",
        }
    )

    assert redacted == {"api_key": "***", "token": "***", "normal": "value"}


def test_redact_sensitive_mapping_does_not_mask_plain_key_suffixes():
    redacted = redact_sensitive_mapping(
        {
            "idempotency_key": "idem-1",
            "dedupe_key": "dedupe-1",
            "keyword": "momentum",
            "private_key": "secret",
        }
    )

    assert redacted == {
        "idempotency_key": "idem-1",
        "dedupe_key": "dedupe-1",
        "keyword": "momentum",
        "private_key": "***",
    }
