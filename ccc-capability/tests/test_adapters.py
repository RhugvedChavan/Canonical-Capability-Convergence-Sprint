import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.adapters.bucket_adapter import BucketAdapter
from app.adapters.insightflow_adapter import InsightFlowAdapter
from app.adapters.rajya_adapter import RajyaAdapter
from app.adapters.replay_adapter import ReplayAdapter
from app.adapters.runtime_registry_adapter import RuntimeRegistryAdapter
from app.capability.events import CapabilityEvent, EventBus, EventType


def make_event(event_type=EventType.DOCUMENT_CREATED, entity_id=1, actor_id=1, payload=None):
    return CapabilityEvent(
        event_type=event_type,
        entity_type="document",
        entity_id=entity_id,
        actor_id=actor_id,
        payload=payload or {"title": "Test Doc", "content": "hello world"},
    )


# ---------- Bucket ----------
def test_bucket_adapter_stores_relevant_events():
    adapter = BucketAdapter()
    event = make_event()
    result = adapter.handle_event(event)
    assert result["status"] == "stored"
    assert adapter.get_object(result["object_key"]) is not None


def test_bucket_adapter_ignores_irrelevant_events():
    adapter = BucketAdapter()
    event = make_event(event_type=EventType.COMMENT_ADDED, payload={"text": "hi"})
    result = adapter.handle_event(event)
    assert result["status"] == "ignored"


# ---------- Replay ----------
def test_replay_adapter_appends_and_replays():
    adapter = ReplayAdapter()
    e1 = make_event(entity_id=1)
    e2 = make_event(entity_id=2)
    adapter.handle_event(e1)
    adapter.handle_event(e2)
    assert adapter.log_length() == 2
    replayed = adapter.replay()
    assert len(replayed) == 2
    assert replayed[0]["event_id"] == e1.event_id


def test_replay_events_by_type_filters_correctly():
    adapter = ReplayAdapter()
    adapter.handle_event(make_event(event_type=EventType.DOCUMENT_CREATED))
    adapter.handle_event(make_event(event_type=EventType.TASK_CREATED, entity_id=2))
    created = adapter.events_by_type("document_created")
    assert len(created) == 1


# ---------- InsightFlow ----------
def test_insightflow_aggregates_counts():
    adapter = InsightFlowAdapter()
    adapter.handle_event(make_event(event_type=EventType.DOCUMENT_CREATED))
    adapter.handle_event(make_event(event_type=EventType.DOCUMENT_CREATED, entity_id=2))
    adapter.handle_event(make_event(event_type=EventType.TASK_CREATED, entity_id=3))
    snap = adapter.snapshot()
    assert snap["counts_by_event_type"]["document_created"] == 2
    assert snap["counts_by_event_type"]["task_created"] == 1


# ---------- Runtime Registry ----------
def test_runtime_registry_registers_and_heartbeats():
    adapter = RuntimeRegistryAdapter(module_identifier="test.module", capability_version="1.0.0")
    reg_result = adapter.register()
    assert reg_result["status"] == "registered"
    adapter.handle_event(make_event())
    status = adapter.status()
    assert status["registered"] is True
    assert status["event_count"] == 1


def test_runtime_registry_reports_unhealthy_before_registration():
    adapter = RuntimeRegistryAdapter(module_identifier="test.module", capability_version="1.0.0")
    assert adapter.is_healthy() is False
    adapter.register()
    assert adapter.is_healthy() is True


def test_base_adapters_default_to_healthy():
    assert BucketAdapter().is_healthy() is True
    assert ReplayAdapter().is_healthy() is True
    assert InsightFlowAdapter().is_healthy() is True
    assert RajyaAdapter().is_healthy() is True


# ---------- Rajya ----------
def test_rajya_audits_every_event():
    adapter = RajyaAdapter()
    adapter.handle_event(make_event())
    assert len(adapter.audit_trail()) == 1


def test_rajya_flags_destructive_event_without_actor():
    adapter = RajyaAdapter()
    event = make_event(event_type=EventType.DOCUMENT_DELETED, actor_id=None, payload={"title": "gone"})
    result = adapter.handle_event(event)
    assert result["policy_flag"] is not None
    assert len(adapter.flags()) == 1


def test_rajya_does_not_flag_destructive_event_with_actor():
    adapter = RajyaAdapter()
    event = make_event(event_type=EventType.DOCUMENT_DELETED, actor_id=7, payload={"title": "gone"})
    result = adapter.handle_event(event)
    assert result["policy_flag"] is None


# ---------- Event bus replay-safety / isolation ----------
def test_event_bus_dispatches_to_all_registered_adapters():
    bus = EventBus()
    bucket = BucketAdapter()
    replay = ReplayAdapter()
    bus.register_adapter(bucket)
    bus.register_adapter(replay)
    report = bus.emit(
        EventType.DOCUMENT_CREATED, entity_type="document", entity_id=1, actor_id=1,
        payload={"title": "T", "content": "C"},
    )
    assert len(report.outcomes) == 2
    assert all(o.ok for o in report.outcomes)


def test_adapter_idempotent_on_duplicate_event_id():
    adapter = BucketAdapter()
    event = make_event()
    first = adapter.handle_event(event)
    second = adapter.handle_event(event)  # same event_id, replayed
    assert first["status"] == "stored"
    assert second["status"] == "duplicate_ignored"


def test_one_failing_adapter_does_not_break_others():
    class ExplodingAdapter:
        name = "exploding"

        def handle_event(self, event):
            raise RuntimeError("boom")

    bus = EventBus()
    bus.register_adapter(ExplodingAdapter())
    bus.register_adapter(ReplayAdapter())
    report = bus.emit(
        EventType.DOCUMENT_CREATED, entity_type="document", entity_id=1, actor_id=1, payload={},
    )
    outcomes = {o.adapter_name: o for o in report.outcomes}
    assert outcomes["exploding"].ok is False
    assert outcomes["replay"].ok is True


def test_before_hook_can_veto_event():
    bus = EventBus()
    bus.register_adapter(ReplayAdapter())
    bus.add_before_hook(lambda event: None)  # veto everything
    report = bus.emit(
        EventType.DOCUMENT_CREATED, entity_type="document", entity_id=1, actor_id=1, payload={},
    )
    assert report.outcomes == []


def test_after_hook_observes_outcomes():
    bus = EventBus()
    bus.register_adapter(ReplayAdapter())
    seen = []
    bus.add_after_hook(lambda event, outcomes: seen.append((event, outcomes)))
    bus.emit(EventType.DOCUMENT_CREATED, entity_type="document", entity_id=1, actor_id=1, payload={})
    assert len(seen) == 1
