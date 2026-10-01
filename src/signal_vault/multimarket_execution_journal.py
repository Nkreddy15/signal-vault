"""Provider-neutral durable order lifecycle journal for paper/demo execution.

The journal contains no network client and no live broker host.  It exists so
US-equity paper and Kalshi demo adapters can share the same crash/idempotency
rule as the BTC paper prototype: persist SUBMISSION_PENDING before any POST,
treat uncertain transport as UNKNOWN_RESULT, and never allow another order
until the prior provider state is reconciled.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping
import hashlib
import json
import sqlite3

from .paper_order_state import BrokerObservation,PaperOrderState,Stage

LANES=frozenset({"crypto","us_equity","kalshi_event_contract"})

@dataclass(frozen=True)
class MultiMarketOrderDraft:
    client_order_id:str
    market_lane:str
    instrument:str
    max_loss_usd:Decimal
    payload:Mapping[str,str]

    def __post_init__(self) -> None:
        if (not isinstance(self.client_order_id,str) or
                not 1<=len(self.client_order_id)<=64 or
                not all(ch.isalnum() or ch in "_-" for ch in self.client_order_id)):
            raise ValueError("invalid client order id")
        if self.market_lane not in LANES:
            raise ValueError("unknown market lane")
        if (not isinstance(self.instrument,str) or not self.instrument.strip() or
                len(self.instrument)>160 or any(ch in self.instrument for ch in "\r\n\x00")):
            raise ValueError("invalid instrument")
        if (type(self.max_loss_usd) is not Decimal or
                not self.max_loss_usd.is_finite() or self.max_loss_usd<=0):
            raise ValueError("positive finite max loss required")
        if (not isinstance(self.payload,Mapping) or not self.payload or
                any(not isinstance(k,str) or not isinstance(v,str)
                    for k,v in self.payload.items())):
            raise ValueError("string-only provider payload required")
        forbidden=("secret","signature","private_key","api_key")
        if any(any(word in k.lower() for word in forbidden) for k in self.payload):
            raise ValueError("credentials must never enter execution draft payload")

    @property
    def payload_sha256(self) -> str:
        raw=json.dumps(dict(self.payload),sort_keys=True,separators=(",",":")).encode()
        return hashlib.sha256(raw).hexdigest()

def _state_json(state:PaperOrderState) -> str:
    return json.dumps({
        "client_order_id":state.client_order_id,
        "stage":state.stage.value,
        "broker_order_id":state.broker_order_id,
        "provider_status":state.provider_status,
        "cumulative_filled_qty":str(state.cumulative_filled_qty),
        "filled_avg_price":(
            str(state.filled_avg_price) if state.filled_avg_price is not None else None),
        "reconciled":state.reconciled,
    },sort_keys=True,separators=(",",":"))

def _state(raw:str) -> PaperOrderState:
    data=json.loads(raw)
    return PaperOrderState(
        client_order_id=data["client_order_id"],
        stage=Stage(data["stage"]),
        broker_order_id=data["broker_order_id"],
        provider_status=data["provider_status"],
        cumulative_filled_qty=Decimal(data["cumulative_filled_qty"]),
        filled_avg_price=(
            Decimal(data["filled_avg_price"]) if data["filled_avg_price"] is not None else None),
        reconciled=bool(data["reconciled"]),
    )

class MultiMarketExecutionJournal:
    def __init__(self,path:str|Path) -> None:
        self.path=Path(path)
        self.connection=sqlite3.connect(self.path)
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS mm_execution_drafts(
          client_order_id TEXT PRIMARY KEY,
          market_lane TEXT NOT NULL,
          instrument TEXT NOT NULL,
          max_loss_usd TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          payload_sha256 TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status='DRAFT_APPROVED'),
          created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mm_execution_states(
          client_order_id TEXT PRIMARY KEY,
          state_json TEXT NOT NULL,
          updated_utc TEXT NOT NULL,
          FOREIGN KEY(client_order_id) REFERENCES mm_execution_drafts(client_order_id)
        );
        CREATE TABLE IF NOT EXISTS mm_execution_preflights(
          client_order_id TEXT PRIMARY KEY,
          receipt_json TEXT NOT NULL,
          receipt_sha256 TEXT NOT NULL,
          captured_utc TEXT NOT NULL,
          FOREIGN KEY(client_order_id) REFERENCES mm_execution_drafts(client_order_id)
        );
        CREATE TABLE IF NOT EXISTS mm_execution_events(
          seq INTEGER PRIMARY KEY AUTOINCREMENT,
          client_order_id TEXT NOT NULL,
          event_type TEXT NOT NULL,
          details_json TEXT NOT NULL,
          created_utc TEXT NOT NULL
        );
        """)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self,*_):
        self.close()

    @staticmethod
    def _stamp(at:datetime) -> str:
        if not isinstance(at,datetime) or at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone-aware timestamp required")
        return at.astimezone(timezone.utc).isoformat()

    def record_approved_draft(self,draft:MultiMarketOrderDraft,*,at:datetime) -> None:
        stamp=self._stamp(at)
        payload=json.dumps(dict(draft.payload),sort_keys=True,separators=(",",":"))
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                "INSERT INTO mm_execution_drafts VALUES (?,?,?,?,?,?,?,?)",
                (draft.client_order_id,draft.market_lane,draft.instrument,
                 str(draft.max_loss_usd),payload,draft.payload_sha256,
                 "DRAFT_APPROVED",stamp))
            self.connection.execute(
                "INSERT INTO mm_execution_events(client_order_id,event_type,details_json,created_utc) VALUES (?,?,?,?)",
                (draft.client_order_id,"DRAFT_APPROVED",
                 json.dumps({"market_lane":draft.market_lane,
                             "payload_sha256":draft.payload_sha256},sort_keys=True),
                 stamp))
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def get_state(self,client_order_id:str) -> PaperOrderState:
        row=self.connection.execute(
            "SELECT state_json FROM mm_execution_states WHERE client_order_id=?",
            (client_order_id,)).fetchone()
        if row is None:
            raise KeyError("execution state not found")
        state=_state(row[0])
        if state.client_order_id!=client_order_id:
            raise ValueError("execution state identity mismatch")
        return state

    def get_approved_draft(self,client_order_id:str) -> MultiMarketOrderDraft:
        row=self.connection.execute(
            "SELECT market_lane,instrument,max_loss_usd,payload_json,"
            "payload_sha256,status FROM mm_execution_drafts "
            "WHERE client_order_id=?",
            (client_order_id,),
        ).fetchone()
        if row is None:
            raise KeyError("approved execution draft not found")
        lane,instrument,max_loss_raw,payload_raw,payload_sha,status=row
        if status!="DRAFT_APPROVED":
            raise PermissionError("execution draft is not approved")
        try:
            payload=json.loads(payload_raw)
            max_loss=Decimal(max_loss_raw)
        except Exception as exc:
            raise ValueError("malformed stored execution draft") from exc
        if (
            not isinstance(payload,dict)
            or any(not isinstance(k,str) or not isinstance(v,str)
                    for k,v in payload.items())
        ):
            raise ValueError("stored execution payload must be string-only")
        draft=MultiMarketOrderDraft(
            client_order_id=client_order_id,
            market_lane=lane,
            instrument=instrument,
            max_loss_usd=max_loss,
            payload=payload,
        )
        if draft.payload_sha256!=payload_sha:
            raise ValueError("stored execution draft payload hash mismatch")
        return draft

    def record_provider_preflight(
        self,client_order_id:str,receipt:Mapping[str,object],*,at:datetime,
    ) -> str:
        stamp=self._stamp(at)
        if not isinstance(receipt,Mapping):
            raise ValueError("provider preflight receipt mapping required")
        draft=self.get_approved_draft(client_order_id)
        if draft.client_order_id!=client_order_id:
            raise ValueError("provider preflight draft identity mismatch")
        if self.connection.execute(
            "SELECT 1 FROM mm_execution_states WHERE client_order_id=?",
            (client_order_id,),
        ).fetchone():
            raise PermissionError("provider preflight must be persisted before submission starts")
        raw=json.dumps(dict(receipt),sort_keys=True,separators=(",",":"))
        if len(raw.encode())>64*1024:
            raise ValueError("provider preflight receipt unexpectedly large")
        sha=hashlib.sha256(raw.encode()).hexdigest()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                "INSERT INTO mm_execution_preflights VALUES (?,?,?,?)",
                (client_order_id,raw,sha,stamp),
            )
            self.connection.execute(
                "INSERT INTO mm_execution_events(client_order_id,event_type,details_json,created_utc) VALUES (?,?,?,?)",
                (client_order_id,"PROVIDER_PREFLIGHT_VERIFIED",
                 json.dumps({"receipt_sha256":sha},sort_keys=True),stamp),
            )
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        return sha

    def get_provider_preflight(self,client_order_id:str) -> dict[str,object]:
        row=self.connection.execute(
            "SELECT receipt_json,receipt_sha256 FROM mm_execution_preflights "
            "WHERE client_order_id=?",
            (client_order_id,),
        ).fetchone()
        if row is None:
            raise KeyError("provider preflight receipt not found")
        raw,expected_sha=row
        if hashlib.sha256(raw.encode()).hexdigest()!=expected_sha:
            raise ValueError("provider preflight receipt hash mismatch")
        try:
            value=json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("provider preflight receipt malformed") from exc
        if not isinstance(value,dict):
            raise ValueError("provider preflight receipt must be an object")
        return value

    def has_unresolved(self) -> bool:
        return any(
            _state(row[0]).blocks_new_execution
            for row in self.connection.execute("SELECT state_json FROM mm_execution_states"))

    def begin_submission(self,draft:MultiMarketOrderDraft,*,at:datetime) -> PaperOrderState:
        stamp=self._stamp(at)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row=self.connection.execute(
                "SELECT market_lane,instrument,max_loss_usd,payload_sha256,status "
                "FROM mm_execution_drafts WHERE client_order_id=?",
                (draft.client_order_id,)).fetchone()
            expected=(draft.market_lane,draft.instrument,str(draft.max_loss_usd),
                      draft.payload_sha256,"DRAFT_APPROVED")
            if row!=expected:
                raise PermissionError("matching durable approved draft required")
            if self.connection.execute(
                "SELECT 1 FROM mm_execution_states WHERE client_order_id=?",
                (draft.client_order_id,)).fetchone():
                raise ValueError("submission already started")
            if self.has_unresolved():
                raise PermissionError("unresolved cross-market order blocks new execution")
            state=PaperOrderState(draft.client_order_id).start_submission()
            self.connection.execute(
                "INSERT INTO mm_execution_states VALUES (?,?,?)",
                (draft.client_order_id,_state_json(state),stamp))
            self.connection.execute(
                "INSERT INTO mm_execution_events(client_order_id,event_type,details_json,created_utc) VALUES (?,?,?,?)",
                (draft.client_order_id,"SUBMISSION_PENDING",
                 json.dumps({"commit_before_network":True}),stamp))
            self.connection.execute("COMMIT")
            return state
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def _save(self,state:PaperOrderState,event:str,details:dict[str,object],at:datetime) -> None:
        stamp=self._stamp(at)
        self.connection.execute(
            "UPDATE mm_execution_states SET state_json=?,updated_utc=? WHERE client_order_id=?",
            (_state_json(state),stamp,state.client_order_id))
        self.connection.execute(
            "INSERT INTO mm_execution_events(client_order_id,event_type,details_json,created_utc) VALUES (?,?,?,?)",
            (state.client_order_id,event,json.dumps(details,sort_keys=True),stamp))

    def mark_unknown(self,client_order_id:str,*,at:datetime) -> PaperOrderState:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            state=self.get_state(client_order_id).mark_transport_uncertain()
            self._save(state,"UNKNOWN_RESULT",{"blind_retry_forbidden":True},at)
            self.connection.execute("COMMIT")
            return state
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def recover_pending_after_restart(self,*,at:datetime) -> tuple[str,...]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            changed=[]
            rows=tuple(self.connection.execute(
                "SELECT client_order_id,state_json FROM mm_execution_states"))
            for client_id,raw in rows:
                old=_state(raw)
                if old.stage is Stage.SUBMISSION_PENDING:
                    new=old.mark_transport_uncertain()
                    self._save(new,"RESTART_RECOVERY_UNKNOWN",
                               {"provider_lookup_required":True},at)
                    changed.append(client_id)
            self.connection.execute("COMMIT")
            return tuple(sorted(changed))
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def observe_provider(self,receipt:BrokerObservation,*,at:datetime) -> PaperOrderState:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            state=self.get_state(receipt.client_order_id).observe(receipt)
            self._save(state,"PROVIDER_OBSERVATION",
                       {"provider_status":state.provider_status,
                        "cumulative_filled_qty":str(state.cumulative_filled_qty)},at)
            self.connection.execute("COMMIT")
            return state
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def confirm_reconciled(
        self,client_order_id:str,*,at:datetime,
        provider_cash_verified:bool,provider_position_verified:bool,
        provider_order_verified:bool,
    ) -> PaperOrderState:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            state=self.get_state(client_order_id).confirm_reconciled(
                provider_cash_verified=provider_cash_verified,
                provider_position_verified=provider_position_verified,
                provider_order_verified=provider_order_verified)
            self._save(state,"RECONCILED",{"all_provider_surfaces_verified":True},at)
            self.connection.execute("COMMIT")
            return state
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
