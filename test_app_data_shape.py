import unittest
import numpy as np
import pandas as pd

from app import flatten_columns, prepare_indicators


class AppDataShapeTests(unittest.TestCase):
    def _multi_ticker_frame(self):
        idx = pd.date_range("2026-01-01", periods=80, freq="D")
        fields = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
        cols = pd.MultiIndex.from_product([fields, ["KLAC", "OTHER"]], names=["Price", "Ticker"])
        data = np.zeros((len(idx), len(cols)), dtype=float)
        df = pd.DataFrame(data, index=idx, columns=cols)
        for ticker, base in [("KLAC", 100.0), ("OTHER", 500.0)]:
            df[("Open", ticker)] = base + np.arange(len(idx)) * 0.1
            df[("High", ticker)] = base + 2 + np.arange(len(idx)) * 0.1
            df[("Low", ticker)] = base - 2 + np.arange(len(idx)) * 0.1
            df[("Close", ticker)] = base + 1 + np.arange(len(idx)) * 0.1
            df[("Adj Close", ticker)] = base + 1 + np.arange(len(idx)) * 0.1
            df[("Volume", ticker)] = 1_000_000 + np.arange(len(idx))
        return df

    def test_selects_requested_ticker_before_flatten(self):
        raw = self._multi_ticker_frame()
        flat = flatten_columns(raw, "KLAC")
        self.assertFalse(isinstance(flat.columns, pd.MultiIndex))
        self.assertFalse(flat.columns.duplicated().any())
        self.assertIsInstance(flat["Close"], pd.Series)
        self.assertAlmostEqual(float(flat["Close"].iloc[0]), 101.0)

    def test_prepare_indicators_handles_selected_ticker(self):
        flat = flatten_columns(self._multi_ticker_frame(), "KLAC")
        prepared = prepare_indicators(flat)
        self.assertIn("EMA20", prepared.columns)
        self.assertIn("EMA50", prepared.columns)
        self.assertIsInstance(prepared["EMA20"], pd.Series)

    def test_single_ticker_yfinance_shape_still_flattens(self):
        idx = pd.date_range("2026-01-01", periods=80, freq="D")
        cols = pd.MultiIndex.from_product(
            [["Open", "High", "Low", "Close", "Adj Close", "Volume"], ["KLAC"]],
            names=["Price", "Ticker"],
        )
        raw = pd.DataFrame(1.0, index=idx, columns=cols)
        flat = flatten_columns(raw, "KLAC")
        self.assertEqual(list(flat.columns), ["Open", "High", "Low", "Close", "Adj Close", "Volume"])


if __name__ == "__main__":
    unittest.main()
