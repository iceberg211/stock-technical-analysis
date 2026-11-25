from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pa_state import event_id, mark_emitted, material_delta, should_emit, transition_setup


def state(status="none", latest="2026-08-03T13:35:00Z"):
    return {
        "symbol": "SNDK",
        "last_complete_bar_time": latest,
        "version": 1,
        "market_context": {
            "primary_state": "broad_bear_channel",
            "alternate_state": "trading_range",
            "switch_condition": "完整K线站上主要较低高点并获得跟进",
            "always_in": "short",
            "location": "middle",
            "transition": "stable",
            "confidence": "medium",
        },
        "setup": {
            "type": "l2_short",
            "status": status,
            "trade_style": "swing",
            "order_type": "stop",
            "trigger": None,
            "initial_risk": "入场到主要较低高点上方",
            "logical_stop": None,
            "logical_risk": "主要较低高点被有效突破",
            "target_space": "到前低仍有空间",
            "targets": [],
            "invalidation": "站上主要摆动高点并获得跟进",
        },
        "position": {"premise_status": None},
        "data_quality_warning": None,
    }


class PriceActionStateTest(unittest.TestCase):
    def test_legal_setup_lifecycle(self):
        candidate = transition_setup(
            state(), "candidate", "2026-08-03T13:40:00Z", "位置允许"
        )
        armed = transition_setup(
            candidate, "armed", "2026-08-03T13:45:00Z", "确认已具备"
        )
        triggered = transition_setup(
            armed, "triggered", "2026-08-03T13:50:00Z", "价格触发"
        )
        self.assertEqual("triggered", triggered["setup"]["status"])
        self.assertEqual(4, triggered["version"])

    def test_illegal_transition_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "非法战法状态转换"):
            transition_setup(
                state(), "triggered", "2026-08-03T13:40:00Z", "跳过确认"
            )

    def test_plain_new_bar_does_not_emit_material_delta(self):
        previous = state("candidate")
        current = state("candidate", "2026-08-03T13:40:00Z")
        delta = material_delta(previous, current)
        self.assertFalse(delta["material_change"])

    def test_always_in_or_setup_change_emits_delta(self):
        previous = state("candidate")
        current = state("armed")
        current["market_context"]["always_in"] = "unclear"
        delta = material_delta(previous, current)
        self.assertTrue(delta["material_change"])
        fields = {item["field"] for item in delta["changes"]}
        self.assertIn("market_context.always_in", fields)
        self.assertIn("setup.status", fields)

    def test_alternate_explanation_and_trade_method_emit_delta(self):
        previous = state("candidate")
        current = state("candidate")
        current["market_context"]["alternate_state"] = "bull_reversal"
        current["market_context"]["switch_condition"] = "强多头突破并跟进"
        current["setup"]["trade_style"] = "scalp"
        current["setup"]["order_type"] = "limit"
        delta = material_delta(previous, current)
        fields = {item["field"] for item in delta["changes"]}
        self.assertIn("market_context.alternate_state", fields)
        self.assertIn("market_context.switch_condition", fields)
        self.assertIn("setup.trade_style", fields)
        self.assertIn("setup.order_type", fields)

    def test_risk_or_target_space_change_updates_event_id(self):
        previous = state("armed")
        current = state("armed")
        current["setup"]["target_space"] = "前方空间不足"
        self.assertNotEqual(event_id(previous), event_id(current))

    def test_invalid_trade_fields_are_rejected(self):
        invalid_style = state("candidate")
        invalid_style["setup"]["trade_style"] = "hold_forever"
        with self.assertRaisesRegex(ValueError, "非法持仓方式"):
            material_delta(state("candidate"), invalid_style)

        invalid_order = state("candidate")
        invalid_order["setup"]["order_type"] = "guess"
        with self.assertRaisesRegex(ValueError, "非法订单方式"):
            event_id(invalid_order)

    def test_event_id_is_stable_without_material_change(self):
        first = state("candidate")
        first["setup"]["last_transition_time"] = "2026-08-03T13:35:00Z"
        second = state("candidate", "2026-08-03T13:40:00Z")
        second["setup"]["last_transition_time"] = "2026-08-03T13:35:00Z"
        self.assertEqual(event_id(first), event_id(second))

    def test_emitted_event_is_not_repeated(self):
        current = state("candidate")
        current["setup"]["last_transition_time"] = "2026-08-03T13:35:00Z"
        self.assertTrue(should_emit(current))
        saved = mark_emitted(current)
        self.assertFalse(should_emit(saved))


if __name__ == "__main__":
    unittest.main()
