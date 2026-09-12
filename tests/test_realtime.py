"""Interactive real-time latency engine tests (v0.8, convergence).

Streaming pipeline, bounded jitter/backpressure, turn coordination and
barge-in. Fixture-driven (no microphone, camera, STT backend or live
audio); real-model/real-TTS portions are measured in the acceptance
script (V08_REALTIME_LATENCY_REPORT).
"""
import unittest

from voice.realtime import (
    BP_EXPEDITE, BP_OK, BP_PAUSE_PRODUCER, BP_SHED, IDLE, LISTENING,
    SPEAKING, THINKING, BackpressureController, JitterBuffer,
    LatencyBudget, RealtimePipeline, RealtimeScheduler, RealtimeSession,
    StreamCoordinator, TurnCoordinator, chunk_phrases,
)


class BudgetTests(unittest.TestCase):
    def test_all_within_budget_ok(self):
        b = LatencyBudget()
        m = {"input_capture_ms": 10.0, "stt_partial_ms": 100.0,
             "stt_final_ms": 200.0, "model_ttft_ms": 300.0,
             "first_phrase_ms": 500.0, "tts_first_audio_ms": 100.0,
             "audio_buffer_ms": 10.0, "avatar_event_ms": 20.0,
             "lip_sync_offset_ms": 30.0, "turn_ms": 2000.0}
        res = b.check(m)
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["per_component"]), 10)

    def test_exceeded_component_reported(self):
        b = LatencyBudget(model_ttft_ms=10.0)
        res = b.check({"model_ttft_ms": 500.0})
        self.assertFalse(res["ok"])
        self.assertFalse(res["per_component"]["model_ttft_ms"])


class JitterBufferTests(unittest.TestCase):
    def test_bounded_drops_oldest(self):
        jb = JitterBuffer(maxsize=8)
        for i in range(40):
            jb.put(f"item-{i}")
        self.assertEqual(len(jb), 8)
        self.assertEqual(jb.drops, 32)
        self.assertEqual(jb.max_depth, 8)
        self.assertEqual(jb.get(), "item-32")

    def test_underrun_counted(self):
        jb = JitterBuffer(maxsize=4)
        self.assertIsNone(jb.get())
        self.assertEqual(jb.underruns, 1)

    def test_flush_returns_count(self):
        jb = JitterBuffer(maxsize=4)
        jb.put("a")
        jb.put("b")
        self.assertEqual(jb.flush(), 2)
        self.assertEqual(len(jb), 0)


class BackpressureTests(unittest.TestCase):
    def test_actions(self):
        bp = BackpressureController(high_watermark=24, max_depth=32)
        self.assertEqual(bp.observe({})["action"], BP_EXPEDITE)
        self.assertEqual(bp.observe({"tts": 5})["action"], BP_OK)
        self.assertEqual(bp.observe({"tts": 24})["action"], BP_PAUSE_PRODUCER)
        self.assertEqual(bp.observe({"tts": 40})["action"], BP_SHED)


class TurnCoordinatorTests(unittest.TestCase):
    def test_happy_path(self):
        tc = TurnCoordinator()
        tc.start_listening()
        tc.start_thinking()
        tc.start_speaking()
        tc.finish()
        self.assertEqual(tc.state, IDLE)

    def test_illegal_jump_raises(self):
        tc = TurnCoordinator()
        with self.assertRaises(ValueError):
            tc.start_speaking()

    def test_barge_in_from_speaking(self):
        tc = TurnCoordinator()
        tc.start_listening()
        tc.start_thinking()
        tc.start_speaking()
        res = tc.barge_in(flushed=3)
        self.assertTrue(res["ok"])
        self.assertEqual(res["flushed"], 3)
        self.assertEqual(tc.state, LISTENING)
        self.assertEqual(tc.barge_ins, 1)

    def test_barge_in_outside_speaking_raises(self):
        tc = TurnCoordinator()
        with self.assertRaises(ValueError):
            tc.barge_in()


class ChunkerTests(unittest.TestCase):
    def test_streams_phrases_without_full_response(self):
        phrases, rest = chunk_phrases("Hello world. How are you")
        self.assertEqual(phrases, ["Hello world."])
        self.assertIn("How are you", rest)

    def test_coordinator_emits_incrementally(self):
        sc = StreamCoordinator()
        p1 = sc.feed("First sentence. Second")
        self.assertEqual(p1, ["First sentence."])
        p2 = sc.feed(" half. Third")
        self.assertEqual(p2, ["Second half."])
        tail = sc.flush()
        self.assertEqual(tail, ["Third"])
        self.assertEqual(sc.phrases_emitted, 3)


class PipelineTests(unittest.TestCase):
    def _events(self):
        seen = []

        def avatar_fn(ev, payload):
            seen.append(ev)

        return seen, avatar_fn

    def test_streaming_starts_tts_before_full_response(self):
        sess = RealtimeSession(agent_session_id="agent-1")
        seen, avatar_fn = self._events()
        tts_calls = []

        def tts_fn(text):
            tts_calls.append(text)
            return {"ok": True, "first_audio_ms": 5.0}

        pipe = RealtimePipeline()
        ev = pipe.run_streaming_turn(
            sess, ["hel", "hello"],
            ["Hello ", "world. ", "Second sentence."],
            tts_fn=tts_fn, avatar_fn=avatar_fn)
        # One TTS call per phrase (>=2), never zero.
        self.assertGreaterEqual(len(tts_calls), 2)
        self.assertGreaterEqual(ev.phrases, 2)
        self.assertGreater(ev.latencies_ms["model_ttft_ms"], 0.0)
        self.assertGreater(ev.latencies_ms["turn_ms"], 0.0)
        for key in ("model_ttft_ms", "first_phrase_ms", "tts_first_audio_ms",
                    "avatar_event_ms", "lip_sync_offset_ms", "turn_ms"):
            self.assertIn(key, ev.latencies_ms)
        self.assertEqual(sess.coordinator.state, IDLE)
        for expected in ("LISTENING", "THINKING", "SPEAKING", "IDLE"):
            self.assertIn(expected, seen)

    def test_barge_in_flushes_and_counts(self):
        sess = RealtimeSession(agent_session_id="agent-2")
        seen, avatar_fn = self._events()
        pipe = RealtimePipeline()
        ev = pipe.run_streaming_turn(
            sess, ["stop"],
            ["First phrase. ", "Second phrase that never plays. "],
            tts_fn=lambda text: {"ok": True, "first_audio_ms": 5.0},
            avatar_fn=avatar_fn, barge_in_at_token=0)
        self.assertIsNotNone(ev.barge_in)
        self.assertTrue(ev.barge_in["ok"])
        self.assertEqual(sess.barge_in_count, 1)
        self.assertEqual(sess.coordinator.state, IDLE)
        self.assertIn("LISTENING", seen)


class SchedulerTests(unittest.TestCase):
    def test_interactive_lane_reserved_first(self):
        from resources.descriptors import WorkloadDescriptor

        class W(WorkloadDescriptor):
            pass

        rs = RealtimeScheduler()
        plan = rs.plan([W(workload_id="w-tts", kind="TTS")],
                       [W(workload_id="w-reason", kind="MODEL_INFERENCE")])
        self.assertTrue(plan["interactive_first"])
        flat = [w for wave in plan["waves"] for w in wave]
        self.assertLess(flat.index("w-tts"), flat.index("w-reason"))


if __name__ == "__main__":
    unittest.main()
