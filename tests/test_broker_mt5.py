"""trader-broker on MetaTrader 5 (broker "mt5"): shares to lots, the stop attached,
and never a SELL that could open a short."""
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

ticket = load("trader-broker", "ticket")
check = load("trader-risk", "check")

CFG_PATH = os.path.join(ROOT, "trader-budget", "config.example.json")
ORDERS_PATH = os.path.join(FIX, "trader-risk", "orders-tsla.json")
NOW = "2026-10-19 10:15"
MT5 = {"broker": "mt5", "paper": True, "mt5": {"contract_size": 1, "volume_step": 0.01, "volume_min": 0.01}}


def tsla(**over):
    with open(ORDERS_PATH) as fh:
        o = json.load(fh)["orders"][0]
    o.update(over)
    return o


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = ticket.main(argv)
    return code, out.getvalue(), err.getvalue()


class Volume(unittest.TestCase):
    def test_shares_become_lots(self):
        self.assertEqual(ticket.mt5_volume("8", MT5), (8.0, None))
        cfg = {"mt5": {"contract_size": 100, "volume_step": 0.01}}
        self.assertEqual(ticket.mt5_volume("8", cfg), (0.08, None))

    def test_no_contract_size_is_a_problem(self):
        lots, why = ticket.mt5_volume("8", {"broker": "mt5"})
        self.assertIsNone(lots)
        self.assertIn("contract_size", why)

    def test_off_step_is_refused_not_rounded(self):
        cfg = {"mt5": {"contract_size": 100, "volume_step": 0.1}}
        lots, why = ticket.mt5_volume("8", cfg)
        self.assertIsNone(lots)
        self.assertIn("not a multiple", why)
        self.assertIn("10 shares would fit", why)

    def test_under_the_minimum(self):
        cfg = {"mt5": {"contract_size": 100, "volume_step": 0.01, "volume_min": 0.1}}
        self.assertIn("minimum", ticket.mt5_volume("8", cfg)[1])


class Steps(unittest.TestCase):
    def test_market_bracket_attaches_the_stop_right_after(self):
        steps, why = ticket.mt5_steps(tsla(), MT5)
        self.assertIsNone(why)
        self.assertEqual([s["tool"] for s in steps],
                         ["place_market_order", "get_positions_by_symbol", "modify_position"])
        self.assertEqual(steps[0]["input"], {"symbol": "TSLA", "volume": 8.0, "type": "BUY"})
        self.assertEqual(steps[2]["input"]["stop_loss"], 358.32)
        self.assertEqual(steps[2]["input"]["take_profit"], 370.04)

    def test_limit_entry_is_one_pending_order_with_sl_tp(self):
        steps, _ = ticket.mt5_steps(tsla(type="limit", limit_price="363"), MT5)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["tool"], "place_pending_order")
        self.assertEqual(steps[0]["input"], {"symbol": "TSLA", "volume": 8.0, "type": "BUY", "price": 363.0,
                                             "stop_loss": 358.32, "take_profit": 370.04})

    def test_symbol_map(self):
        cfg = dict(MT5, mt5=dict(MT5["mt5"], symbol_map={"TSLA": "TSLA.US"}))
        steps, _ = ticket.mt5_steps(tsla(), cfg)
        self.assertEqual(steps[0]["input"]["symbol"], "TSLA.US")

    def test_an_exit_closes_by_id_and_never_sends_sell(self):
        sell = {"symbol": "TSLA", "side": "sell", "qty": "8", "type": "market", "time_in_force": "day"}
        steps, _ = ticket.mt5_steps(sell, MT5, "exit")
        tools = [s["tool"] for s in steps]
        self.assertEqual(tools, ["get_positions_by_symbol", "close_position"])
        self.assertNotIn("place_market_order", tools)

    def test_a_sell_entry_would_be_a_short_and_is_refused(self):
        sell = {"symbol": "TSLA", "side": "sell", "qty": "8", "type": "market", "time_in_force": "day"}
        steps, why = ticket.mt5_steps(sell, MT5, "entry")
        self.assertIsNone(steps)
        self.assertIn("short", why)

    def test_dollar_amounts_and_odd_types_are_refused(self):
        self.assertIn("notional", ticket.mt5_steps({"symbol": "AAPL", "side": "buy", "notional": "1250",
                                                    "type": "market"}, MT5)[1])
        self.assertIn("not supported", ticket.mt5_steps(tsla(type="trailing_stop"), MT5)[1])


class Flow(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.orders = os.path.join(self.d, "orders.json")
        shutil.copy(ORDERS_PATH, self.orders)
        with open(CFG_PATH) as fh:
            c = json.load(fh)
        c.update(MT5)
        self.cfg = os.path.join(self.d, "config.json")
        with open(self.cfg, "w") as fh:
            json.dump(c, fh)
        self.risk = os.path.join(self.d, "state", "risk.json")
        self.state = os.path.join(self.d, "state", "broker.json")
        self.pf = os.path.join(self.d, "portfolio.json")
        self.none = os.path.join(self.d, "none")

    def tearDown(self):
        shutil.rmtree(self.d)

    def args(self, *extra):
        return list(extra) + ["--orders", self.orders, "--config", self.cfg, "--risk", self.risk,
                              "--state", self.state, "--now", NOW]

    def run_risk(self):
        with redirect_stdout(io.StringIO()):
            return check.main(["--orders", self.orders, "--config", self.cfg, "--portfolio", self.pf,
                               "--prices", self.none, "--state", self.state, "--now", NOW, "--out", self.risk])

    def set_mt5(self, **m):
        with open(self.cfg) as fh:
            c = json.load(fh)
        c["mt5"] = m
        with open(self.cfg, "w") as fh:
            json.dump(c, fh)

    def test_the_same_risk_check_applies(self):
        self.assertEqual(self.run_risk(), 0)
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertEqual(code, 0)
        self.assertIn("ORDER 1 of 1, DEMO account, MetaTrader 5", text)
        self.assertIn("READY: trader-risk PASS", text)
        self.assertIn('1. place_market_order {"symbol": "TSLA", "volume": 8.0, "type": "BUY"}', text)
        self.assertIn("modify_position", text)
        self.assertIn("no stop at the broker", text)
        self.assertNotIn("place_stock_order", text)

    def test_approve_prints_the_metatrader_calls(self):
        self.run_risk()
        code, text, _ = run(self.args("approve", "--index", "1", "--reply", "yes"))
        self.assertEqual(code, 0)
        self.assertIn("place_market_order", text)
        self.assertNotIn("place_stock_order", text)

    def test_missing_contract_size_is_never_ready(self):
        self.set_mt5()
        self.run_risk()
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertEqual(code, 1)
        self.assertIn("NOT READY for MetaTrader", text)
        self.assertNotIn("Reply \"yes\"", text)
        code, _, err = run(self.args("approve", "--index", "1", "--reply", "yes"))
        self.assertEqual(code, 1)
        self.assertIn("contract_size", err)

    def test_json_ticket(self):
        self.run_risk()
        code, text, _ = run(self.args("show", "--index", "1", "--json"))
        t = json.loads(text)
        self.assertEqual(t["tool"], "metatrader")
        self.assertEqual(t["mt5_steps"][0]["tool"], "place_market_order")

    def test_flatten_points_to_close_position(self):
        code, text, _ = run(["flatten", "--symbol", "TSLA", "--qty", "8", "--orders", self.orders,
                             "--config", self.cfg, "--plan", self.none, "--portfolio", self.pf, "--now", NOW])
        self.assertEqual(code, 0)
        self.assertIn("close_position", text)
        self.assertNotIn("cancel_order_by_id", text)


if __name__ == "__main__":
    unittest.main()
