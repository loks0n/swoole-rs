"""Executable timer test specification, not an upstream or Rust parity test.

A deliberately small unordered queue and explicit clock define golden traces.
Golden traces follow the frozen queue-kernel contract in docs/timer-abi-v1.md.
This reference model does not drive the actual ABI or PHP/native adapter.
"""
from collections import Counter
from dataclasses import dataclass
import unittest

LIMIT = (1 << 63) - 1
COUNTER_LIMIT = (1 << 64) - 1


class Clock:
    def __init__(self, now=0):
        self.now = now

    def advance(self, now):
        if not self.now <= now <= LIMIT:
            raise ValueError("clock must be monotonic and representable")
        self.now = now


def checked_add(left, right):
    if right <= 0 or left > LIMIT - right:
        raise ValueError("invalid delay or deadline overflow")
    return left + right


@dataclass
class Node:
    id: int
    name: str
    due: int
    interval: int
    born: int
    callback: object
    destructor: object = None
    removed: bool = False
    executions: int = 0


class Model:
    def __init__(self, clock):
        self.clock = clock
        self.nodes = []
        self.round = 0
        self.next_id = 1
        self.active = None
        self.selecting = False
        self.closed = False
        self.events = []
        self.released = Counter()

    def add(self, name, delay, callback=lambda *_: None, repeat=False, destructor=None):
        if self.closed or self.next_id > LIMIT:
            raise ValueError("closed queue or ID exhaustion")
        due = checked_add(self.clock.now, delay)
        node = Node(self.next_id, name, due, delay if repeat else 0,
                    self.round, callback, destructor)
        self.next_id += 1
        self.nodes.append(node)
        return node

    def snapshot(self):
        return tuple(node.id for node in self.nodes)

    def release(self, node):
        # Detach before native destruction; no queue borrow crosses that call.
        index = self.nodes.index(node)
        self.nodes[index] = self.nodes[-1]
        self.nodes.pop()
        self.released[node.id] += 1
        assert self.released[node.id] == 1
        self.events.append("drop:" + node.name)
        if node.destructor:
            node.destructor(self, node)

    def remove(self, node):
        if node not in self.nodes or node.removed:
            return False
        if node is self.active:
            node.removed = True
        else:
            self.release(node)
        return True

    def update(self, node, deadline):
        if self.closed or node not in self.nodes or node.removed:
            return False
        if not 0 <= deadline <= LIMIT:
            raise ValueError("deadline is not representable")
        node.due = deadline
        return True

    def delay(self, node, delay):
        return self.update(node, checked_add(self.clock.now, delay))

    def clear_snapshot(self):
        for timer_id in self.snapshot():
            node = next((n for n in self.nodes if n.id == timer_id), None)
            if node:
                self.remove(node)

    def teardown(self):
        # Close rejects new adds/updates; active destruction waits for completion.
        self.closed = True
        self.clear_snapshot()

    def select(self):
        # Nested begin is BUSY, including during native destructor callbacks.
        if self.selecting:
            return False
        if self.closed:
            return False
        if self.round == COUNTER_LIMIT:
            raise ValueError("round overflow")
        now = self.clock.now
        self.selecting = True
        while self.nodes:
            node = min(self.nodes, key=lambda n: n.due)
            if node.due > now or node.born == self.round:
                break
            self.active = node
            self.events.append("call:" + node.name)
            node.callback(self, node)
            self.active = None
            if node.interval and not node.removed:
                # One callback, coalesced intervals, clock captured at entry.
                steps = max(0, (now - node.due) // node.interval + 1)
                if (steps and node.due > LIMIT - steps * node.interval) or node.executions == COUNTER_LIMIT:
                    # RELEASE_OVERFLOW returns the exact active identity once.
                    self.events.append("overflow:" + node.name)
                    self.release(node)
                else:
                    node.due += steps * node.interval
                    node.executions += 1
            else:
                self.release(node)
        self.round += 1
        self.selecting = False
        return True

    def invariants(self):
        assert len(self.snapshot()) == len(set(self.snapshot()))
        assert all(0 <= n.due <= LIMIT for n in self.nodes)
        assert all(not self.released[n.id] for n in self.nodes)
        assert all(count == 1 for count in self.released.values())
        assert self.active is None or self.active in self.nodes


class GoldenTraces(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.q = Model(self.clock)

    def golden(self, expected):
        self.assertEqual(self.q.events, expected)
        self.q.invariants()

    def due(self, now):
        self.q.select()  # Initial birth-round barrier, even if already due.
        self.clock.advance(now)
        self.q.select()

    def test_active_cancel_observable_until_return(self):
        def callback(q, n):
            self.assertTrue(q.remove(n))
            self.assertFalse(q.remove(n))
            self.assertEqual(q.snapshot(), (n.id,))
            self.assertTrue(n.removed)
            self.assertEqual(q.released[n.id], 0)
        self.q.add("A", 1, callback, repeat=True)
        self.due(1)
        self.assertEqual(self.q.snapshot(), ())
        self.golden(["call:A", "drop:A"])

    def test_active_once_delay_completes_exact_id_without_resurrection(self):
        def callback(q, n):
            self.assertTrue(q.delay(n, 20))
            self.assertEqual(n.due, 22)
            self.assertEqual(min(q.nodes, key=lambda item: item.due).name, "B")
        self.q.add("A", 1, callback)
        self.q.add("B", 2)
        self.due(2)
        self.golden(["call:A", "drop:A", "call:B", "drop:B"])

    def test_active_once_updates_other_due_id_without_wrong_release(self):
        def callback(q, n):
            self.assertTrue(q.update(n, 100))
            self.assertTrue(q.update(b, 0))
            self.assertEqual(q.snapshot(), (n.id, b.id))
            self.assertEqual(q.released[b.id], 0)
        a = self.q.add("A", 1, callback)
        b = self.q.add("B", 2)
        self.due(2)
        self.assertEqual(self.q.released, {a.id: 1, b.id: 1})
        self.golden(["call:A", "drop:A", "call:B", "drop:B"])

    def test_active_repeat_future_deadline_retained(self):
        def callback(q, n):
            self.assertTrue(q.delay(n, 20))
        a = self.q.add("A", 1, callback, repeat=True)
        self.q.add("B", 2)
        self.due(2)
        self.assertEqual((a.due, a.executions, self.q.snapshot()), (22, 1, (a.id,)))
        self.assertEqual(self.q.released[a.id], 0)
        self.clock.advance(21)
        self.q.select()
        self.assertEqual(a.executions, 1)
        self.q.teardown()
        self.golden(["call:A", "call:B", "drop:B", "drop:A"])

    def test_nested_select_rejected(self):
        def callback(q, _):
            before = q.round
            self.assertFalse(q.select())
            self.assertEqual(q.round, before)
        self.q.add("A", 1, callback)
        self.due(1)
        self.golden(["call:A", "drop:A"])

    def test_callback_and_destructor_mutation(self):
        def destructor(q, _):
            q.remove(c)
        def callback(q, _):
            q.remove(b)
        self.q.add("A", 1, callback)
        b = self.q.add("B", 2, destructor=destructor)
        c = self.q.add("C", 3)
        self.due(3)
        self.golden(["call:A", "drop:B", "drop:C", "drop:A"])

    def test_equal_deadline_native_witness_not_fifo_promise(self):
        for name in "ABC":
            self.q.add(name, 1)
        self.due(1)
        self.golden(["call:A", "drop:A", "call:C", "drop:C", "call:B", "drop:B"])

    def test_missed_intervals_coalesced(self):
        node = self.q.add("A", 5, repeat=True)
        self.due(23)
        self.assertEqual((node.due, node.executions), (25, 1))
        self.clock.advance(24)
        self.q.select()
        self.assertEqual(node.executions, 1)
        self.clock.advance(25)
        self.q.select()
        self.assertEqual((node.due, node.executions), (30, 2))
        self.q.teardown()
        self.golden(["call:A", "call:A", "drop:A"])

    def test_clock_captured_before_callback(self):
        def callback(_, __):
            self.clock.advance(100)
        self.q.add("A", 1, callback)
        self.q.add("B", 50)
        self.due(1)
        self.assertEqual(self.q.events, ["call:A", "drop:A"])
        self.q.select()
        self.golden(["call:A", "drop:A", "call:B", "drop:B"])

    def test_birth_round_barrier(self):
        def callback(q, _):
            q.add("C", 1)
        self.q.add("A", 1, callback)
        self.q.add("B", 2)
        self.clock.advance(2)
        self.q.select()
        self.assertEqual(self.q.events, [])  # Due, but born in current round.
        self.q.select()
        self.assertEqual(self.q.events, ["call:A", "drop:A", "call:B", "drop:B"])
        self.clock.advance(3)
        self.q.select()
        self.golden(["call:A", "drop:A", "call:B", "drop:B", "call:C", "drop:C"])

    def test_snapshot_enumeration_survives_mutation(self):
        def destructor(q, _):
            q.add("C", 1)
        a = self.q.add("A", 1, destructor=destructor)
        b = self.q.add("B", 1)
        snapshot = self.q.snapshot()
        self.q.clear_snapshot()
        self.assertEqual(snapshot, (a.id, b.id))
        self.assertEqual([n.name for n in self.q.nodes], ["C"])
        self.q.teardown()
        self.golden(["drop:A", "drop:B", "drop:C"])

    def test_checked_overflow_id_exhaustion_and_rollback(self):
        self.clock.advance(LIMIT - 2)
        before = (self.q.snapshot(), self.q.next_id)
        for delay in (0, -1, 3):
            with self.assertRaises(ValueError):
                self.q.add("bad", delay)
            self.assertEqual((self.q.snapshot(), self.q.next_id), before)
        self.q.next_id = LIMIT
        node = self.q.add("last", 1)
        with self.assertRaises(ValueError):
            self.q.add("exhausted", 1)
        due = node.due
        with self.assertRaises(ValueError):
            self.q.delay(node, 3)
        self.assertEqual(node.due, due)
        with self.assertRaises(ValueError):
            self.clock.advance(LIMIT - 3)
        self.q.teardown()
        self.golden(["drop:last"])

    def test_repeating_deadline_overflow(self):
        self.clock.advance(LIMIT - 2)
        self.q.add("A", 1, repeat=True)
        self.due(LIMIT)
        self.golden(["call:A", "overflow:A", "drop:A"])

    def test_execution_count_overflow_terminal_drop(self):
        a = self.q.add("A", 1, repeat=True)
        a.executions = COUNTER_LIMIT
        self.q.add("B", 2)
        self.due(2)
        self.assertEqual(a.executions, COUNTER_LIMIT)
        self.assertEqual(self.q.snapshot(), ())
        self.assertEqual(self.q.released[a.id], 1)
        self.golden(["call:A", "overflow:A", "drop:A", "call:B", "drop:B"])

    def test_callback_teardown_defers_active_release(self):
        def callback(q, n):
            q.teardown()
            self.assertEqual(q.released[n.id], 0)
            with self.assertRaises(ValueError):
                q.add("C", 1)
        self.q.add("A", 1, callback)
        self.q.add("B", 2)
        self.due(2)
        self.assertEqual(self.q.snapshot(), ())
        self.golden(["call:A", "drop:B", "drop:A"])

    def test_child_teardown_does_not_mutate_parent(self):
        # Independent address-space copies; no real fork, process, or runtime.
        import copy
        self.q.add("A", 1)
        child = copy.deepcopy(self.q)
        child.teardown()
        self.assertEqual(child.events, ["drop:A"])
        self.assertEqual(child.snapshot(), ())
        self.assertEqual(self.q.snapshot(), (1,))
        self.assertEqual(self.q.released[1], 0)
        self.due(1)
        self.golden(["call:A", "drop:A"])
