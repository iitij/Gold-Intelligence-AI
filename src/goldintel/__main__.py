"""Local demonstrations only: no network side effects and no live trading."""
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from goldintel import __version__
from goldintel.domain import (
    AccountState, BrokerSymbolSpec, MarketQuote, RiskPolicy, Side, TradeProposal,
)
from goldintel.risk import assess_paper_proposal


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "health"
    if action == "health":
        print(f"Gold Intelligence AI {__version__}")
        print("XAUUSD ONLY | RESEARCH/PAPER ONLY | LIVE EXECUTION NOT IMPLEMENTED")
        return
    if action == "sample-risk":
        # Synthetic numbers; not real prices, forecasts or a trading recommendation.
        now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        spec = BrokerSymbolSpec(
            "XAUUSD", "XAUUSD", D("0.01"), D("1"), D("0.01"),
            D("10"), D("0.01"), D("30"), True,
        )
        quote = MarketQuote("XAUUSD", now, D("2000.00"), D("2000.10"), True)
        account = AccountState("USD", D("10000"), D("10000"), D("0"), D("0"), 0, True)
        proposal = TradeProposal(
            Side.BUY, "XAUUSD", now, now + timedelta(minutes=1),
            D("2000.10"), D("1998.10"), D("2004.10"),
            "TEST-ONLY-123", "synthetic-model",
        )
        result = assess_paper_proposal(proposal, quote, spec, account, RiskPolicy(), now)
        print("SYNTHETIC EXAMPLE / NO BROKER CALL:", result)
        return
    raise SystemExit("Unknown command; use health or sample-risk")


if __name__ == "__main__":
    main()
