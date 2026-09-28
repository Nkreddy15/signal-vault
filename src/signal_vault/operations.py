"""Restart-safe, exactly-once-per-bar local RESEARCH scheduler (NO broker POST).

This is a paper-only unarmed supervisor. It may read immutable historical
market data and record an audited *draft* or HOLD. It cannot execute an order.
Actual paper broker automation requires separate authenticated onboarding,
provider-derived portfolio snapshots and a reviewed execution-mode release.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence

from .domain import PortfolioSnapshot
from .market_data import Bar, validate_bars
from .offline_pipeline import PlanningResult, plan_latest_closed_bar
from .paper_store import PersistentPaperOrderStore
from .strategy import StrategyConfig


@dataclass(frozen=True)
class ResearchCycle:
    status: str
    bar_close_utc: str
    evidence_id: str
    explanation: str
    repeated: bool = False


def _account_snapshot(book: PersistentPaperOrderStore, price: Decimal) -> tuple[PortfolioSnapshot, Decimal | None]:
    budget=book.budget_snapshot()
    if budget is None:
        return PortfolioSnapshot(Decimal('100'),Decimal('100'),Decimal('100'),Decimal('100')), None
    cash,btc=Decimal(budget['virtual_cash']),Decimal(budget['virtual_btc'])
    equity=cash+btc*price
    marks=book.risk_mark_snapshot()
    if marks is None:
        raise ValueError('missing source-backed risk marks after virtual account opened')
    positions={'BTC/USD':btc*price} if btc else {}
    return PortfolioSnapshot(equity,cash,Decimal(marks['peak_equity']),
                             Decimal(marks['session_start_equity']),long_positions_usd=positions,
                             halted=book.is_operator_halted()), (btc if btc else None)


class LocalResearchSupervisor:
    """Explicitly unarmed: no reference to PaperOnceExecutor or credentials."""
    def __init__(self,book:PersistentPaperOrderStore) -> None:
        self.book=book
        self.book.connection.execute('''CREATE TABLE IF NOT EXISTS research_cycles (
            bar_close_utc TEXT PRIMARY KEY, status TEXT NOT NULL,
            evidence_id TEXT NOT NULL, explanation TEXT NOT NULL,
            created_at_utc TEXT NOT NULL)''')

    def startup(self, *, at:datetime) -> tuple[str,...]:
        """A crash could follow an external POST; never assume it did not."""
        return self.book.recover_inflight_pending_after_restart(at=at)

    def run_once(self,bars:Sequence[Bar],*,at:datetime,
                 cfg:StrategyConfig|None=None) -> ResearchCycle:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError('timezone-aware run time is required')
        # Expire only old unsubmitted DRAFTS. This does not release or mutate
        # submitted/unknown paper orders and is safe across worker restarts.
        self.book.journal.expire_unsent_drafts(at=at)
        strategy=cfg or StrategyConfig()
        history=validate_bars(bars,as_of=at,min_count=strategy.slow_hours+2)
        closed=history[-1].close_time
        close_id=closed.astimezone(timezone.utc).isoformat()
        # The price at a last hour close is not necessarily a fresh executable
        # quote many minutes later. An autonomous scan must miss a stale slot.
        lag=at.astimezone(timezone.utc)-closed
        if lag < timedelta(0) or lag>timedelta(seconds=90):
            return ResearchCycle('STALE_WINDOW',close_id,'',
                                 'Market close outside permitted 90-second decision window')
        row=self.book.connection.execute('''SELECT status,evidence_id,explanation
             FROM research_cycles WHERE bar_close_utc=?''',(close_id,)).fetchone()
        if row:
            return ResearchCycle(*row[:1],close_id,*row[1:],repeated=True)
        if self.book.budget_snapshot() is not None:
            # Mark the independently reconciled virtual position even if the
            # strategy returns HOLD; a profit peak must survive future losses.
            self.book.mark_virtual_quote(mark_price=history[-1].close,at=at,
                evidence_id='closed-bar:'+close_id+':'+str(history[-1].close))
        if self.book.is_operator_halted():
            status,evidence,note='OPERATOR_HALT','', 'Durable manual stop prevents proposals'
        elif self.book.has_unresolved_provider_order():
            status,evidence,note='RECONCILIATION_REQUIRED','', 'Unresolved paper order: no new proposals'
        else:
            portfolio,qty=_account_snapshot(self.book,history[-1].close)
            result=plan_latest_closed_bar(history,now=at,portfolio=portfolio,
                        journal=self.book.journal,strategy=strategy,
                        confirmed_sell_quantity=qty)
            status,evidence,note=result.state,result.evidence_id,result.explanation
        stamp=at.astimezone(timezone.utc).isoformat()
        self.book.connection.execute('BEGIN IMMEDIATE')
        try:
            self.book.connection.execute('''INSERT OR IGNORE INTO research_cycles
                 (bar_close_utc,status,evidence_id,explanation,created_at_utc)
                 VALUES (?,?,?,?,?)''',(close_id,status,evidence,note[:500],stamp))
            row=self.book.connection.execute('''SELECT status,evidence_id,explanation
                 FROM research_cycles WHERE bar_close_utc=?''',(close_id,)).fetchone()
            # Only the thread that wrote the first record emits the event.
            # Other repeated scheduling of the same candle remains idempotent.
            if (row[0],row[1],row[2])==(status,evidence,note[:500]):
                exists=self.book.connection.execute('''SELECT 1 FROM events
                    WHERE client_order_id=? AND event_type='RESEARCH_CYCLE' LIMIT 1''',
                    ('_cycle_'+close_id,)).fetchone()
                if not exists:
                    self.book.connection.execute('''INSERT INTO events
                        (client_order_id,event_type,event_json,created_utc)
                        VALUES(?,?,?,?)''',('_cycle_'+close_id,'RESEARCH_CYCLE',
                         json.dumps({'status':status,'evidence':evidence},sort_keys=True),stamp))
            self.book.connection.execute('COMMIT')
        except BaseException:
            self.book.connection.execute('ROLLBACK')
            raise
        return ResearchCycle(row[0],close_id,row[1],row[2],repeated=False)
