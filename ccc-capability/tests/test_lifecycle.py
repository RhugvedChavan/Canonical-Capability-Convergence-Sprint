import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from app.capability.lifecycle import IllegalLifecycleTransition, LifecycleManager, LifecycleState


def test_initial_state_is_unregistered():
    lm = LifecycleManager()
    assert lm.state == LifecycleState.UNREGISTERED


def test_legal_transition_sequence():
    lm = LifecycleManager()
    lm.transition_to(LifecycleState.REGISTERED, reason="test")
    lm.transition_to(LifecycleState.INITIALIZING, reason="test")
    lm.transition_to(LifecycleState.ACTIVE, reason="test")
    assert lm.state == LifecycleState.ACTIVE
    assert len(lm.history) == 3


def test_illegal_transition_raises():
    lm = LifecycleManager()
    with pytest.raises(IllegalLifecycleTransition):
        lm.transition_to(LifecycleState.ACTIVE, reason="skip states")


def test_active_can_degrade_and_recover():
    lm = LifecycleManager()
    lm.transition_to(LifecycleState.REGISTERED)
    lm.transition_to(LifecycleState.INITIALIZING)
    lm.transition_to(LifecycleState.ACTIVE)
    lm.transition_to(LifecycleState.DEGRADED, reason="dependency down")
    assert lm.state == LifecycleState.DEGRADED
    lm.transition_to(LifecycleState.ACTIVE, reason="dependency restored")
    assert lm.state == LifecycleState.ACTIVE


def test_retired_is_terminal():
    lm = LifecycleManager()
    lm.transition_to(LifecycleState.REGISTERED)
    lm.transition_to(LifecycleState.INITIALIZING)
    lm.transition_to(LifecycleState.ACTIVE)
    lm.transition_to(LifecycleState.DEPRECATING)
    lm.transition_to(LifecycleState.RETIRED)
    assert lm.state == LifecycleState.RETIRED
    with pytest.raises(IllegalLifecycleTransition):
        lm.transition_to(LifecycleState.ACTIVE)


def test_force_retire_from_any_state():
    lm = LifecycleManager()
    lm.transition_to(LifecycleState.REGISTERED)
    lm.force_retire(reason="emergency")
    assert lm.state == LifecycleState.RETIRED


def test_force_retire_twice_raises():
    lm = LifecycleManager()
    lm.force_retire()
    with pytest.raises(IllegalLifecycleTransition):
        lm.force_retire()


def test_is_operational_reflects_active_and_degraded_only():
    lm = LifecycleManager()
    assert lm.is_operational() is False
    lm.transition_to(LifecycleState.REGISTERED)
    lm.transition_to(LifecycleState.INITIALIZING)
    lm.transition_to(LifecycleState.ACTIVE)
    assert lm.is_operational() is True
    lm.transition_to(LifecycleState.DEGRADED)
    assert lm.is_operational() is True
    lm.transition_to(LifecycleState.DEPRECATING)
    assert lm.is_operational() is False


def test_transition_listener_is_notified():
    lm = LifecycleManager()
    received = []
    lm.on_transition(lambda event: received.append(event))
    lm.transition_to(LifecycleState.REGISTERED, reason="notify test")
    assert len(received) == 1
    assert received[0].current == LifecycleState.REGISTERED


def test_lifecycle_event_has_unique_transition_id():
    lm = LifecycleManager()
    e1 = lm.transition_to(LifecycleState.REGISTERED)
    e2 = lm.transition_to(LifecycleState.INITIALIZING)
    assert e1.transition_id != e2.transition_id
    assert e1.transition_id in lm.history[0]["transition_id"]


def test_concurrent_transitions_do_not_corrupt_history():
    """A basic concurrency smoke test: many threads racing to transition
    the same manager should never produce more history entries than legal
    transitions actually succeeded, and the manager should end in a
    consistent, valid state rather than a torn one."""
    import threading

    lm = LifecycleManager()
    lm.transition_to(LifecycleState.REGISTERED)
    lm.transition_to(LifecycleState.INITIALIZING)
    lm.transition_to(LifecycleState.ACTIVE)

    results = []

    def flap():
        try:
            lm.transition_to(LifecycleState.DEGRADED)
            results.append("degraded")
        except Exception:
            results.append("rejected")
        try:
            lm.transition_to(LifecycleState.ACTIVE)
            results.append("active")
        except Exception:
            results.append("rejected")

    threads = [threading.Thread(target=flap) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Whatever interleaving occurred, the manager must be in one of the
    # two states this test cycles between — never a corrupted/unknown one.
    assert lm.state in (LifecycleState.ACTIVE, LifecycleState.DEGRADED)
    # History only grows on successful transitions; every "rejected"
    # outcome must correspond to an IllegalLifecycleTransition, not a
    # silently-lost write. Successes plus the 3 setup transitions must
    # equal the total history length exactly (no torn/duplicated writes).
    successes = sum(1 for r in results if r in ("degraded", "active"))
    assert len(lm.history) == 3 + successes
