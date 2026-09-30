"""Manual bounded GET-only Kalshi resolved-corpus capture and validation pipeline.

Starting from an immutable Phase 38 historical catalog, this module applies the
deterministic Phase 54 corpus plan, captures each selected market with the
Phase 51 settlement-bound evidence collector, scores each bundle with Phase 52,
and aggregates the corpus with Phase 53.

No credentials, authenticated portfolio endpoints, demo orders, or live orders
are used. Partial output after a provider/network failure is intentionally left
in place for forensic inspection and is never silently called complete.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Protocol

from .kalshi_corpus_plan import plan_resolved_market_corpus
from .kalshi_public_research import KalshiPublicResearchClient
from .kalshi_resolved_market_evidence import capture_resolved_market_evidence
from .offline_kalshi_corpus_validation import validate_kalshi_resolved_corpus

MAX_SAMPLE_SIZE=50
DEFAULT_SAMPLE_SIZE=25
DEFAULT_MAX_TRADE_PAGES=20


class CorpusClient(Protocol):
    def historical_market(self,ticker:str)->dict[str,object]: ...
    def historical_market_candlesticks(
        self,*,ticker:str,start_ts:int,end_ts:int,period_interval:int=60,
    )->dict[str,object]: ...
    def historical_trades(
        self,*,ticker:str|None=None,min_ts:int|None=None,max_ts:int|None=None,
        limit:int=1000,cursor:str|None=None,
    )->dict[str,object]: ...


def _new_private_root(path:Path)->None:
    if path.exists() or path.is_symlink():
        raise ValueError("Kalshi corpus output root must be new")
    path.mkdir(mode=0o700)
    if path.stat().st_mode & 0o077:
        raise PermissionError("Kalshi corpus output root must be owner-private")


def _write_once(path:Path,obj:dict[str,object])->str:
    raw=(json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n").encode()
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    fd=os.open(path,flags,0o600)
    with os.fdopen(fd,"wb") as handle:
        os.fchmod(handle.fileno(),0o600)
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return hashlib.sha256(raw).hexdigest()


def capture_and_validate_kalshi_corpus(
    *,
    catalog_root:Path,
    output_root:Path,
    client:CorpusClient,
    sample_size:int=DEFAULT_SAMPLE_SIZE,
    max_trade_pages:int=DEFAULT_MAX_TRADE_PAGES,
)->dict[str,object]:
    if type(sample_size) is not int or not 1<=sample_size<=MAX_SAMPLE_SIZE:
        raise ValueError("bounded Kalshi corpus sample size required")
    if type(max_trade_pages) is not int or not 1<=max_trade_pages<=50:
        raise ValueError("bounded Kalshi trade page count required")

    plan=plan_resolved_market_corpus(catalog_root,sample_size=sample_size)
    _new_private_root(output_root)
    plan_sha=_write_once(output_root/"corpus_plan.json",plan)

    children=[]
    roots=[]
    for index,item in enumerate(plan["markets"],1):
        if not isinstance(item,dict):
            raise ValueError("malformed planned Kalshi market")
        ticker=item.get("ticker")
        start_ts=item.get("capture_start_ts")
        end_ts=item.get("capture_end_ts")
        expected_result=item.get("resolved_result_for_scoring_only")
        if (
            not isinstance(ticker,str)
            or type(start_ts) is not int
            or type(end_ts) is not int
            or expected_result not in {"yes","no"}
        ):
            raise ValueError("malformed planned Kalshi capture contract")

        child=output_root/f"market-{index:03d}-{ticker}"
        result=capture_resolved_market_evidence(
            client=client,
            ticker=ticker,
            start_ts=start_ts,
            end_ts=end_ts,
            output_root=child,
            max_trade_pages=max_trade_pages,
            candlestick_interval=60,
        )
        if result.get("resolved_result")!=expected_result:
            raise ValueError("Kalshi market result changed versus deterministic catalog plan")
        child_manifest=child/"manifest.json"
        child_sha=hashlib.sha256(child_manifest.read_bytes()).hexdigest()
        if child_sha!=result.get("manifest_sha256"):
            raise ValueError("Kalshi child manifest SHA mismatch after capture")
        children.append({
            "index":index,
            "ticker":ticker,
            "folder":child.name,
            "manifest_sha256":child_sha,
        })
        roots.append(child)

    corpus=validate_kalshi_resolved_corpus(roots)
    if corpus.get("resolved_market_count")!=sample_size:
        raise ValueError("Kalshi corpus validation count differs from fixed plan")
    corpus_sha=_write_once(output_root/"corpus_validation.json",corpus)

    manifest={
        "kind":"IMMUTABLE_KALSHI_RESOLVED_CORPUS_EVIDENCE",
        "sample_size":sample_size,
        "catalog_manifest_sha256":plan["source_catalog_manifest_sha256"],
        "corpus_plan_sha256":plan_sha,
        "children":children,
        "corpus_validation_sha256":corpus_sha,
        "credentials_accessed":"NONE",
        "authenticated_portfolio_access":"DISABLED",
        "network_methods":["GET"],
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
    manifest_sha=_write_once(output_root/"manifest.json",manifest)
    return {
        **manifest,
        "manifest_sha256":manifest_sha,
        "corpus_report":corpus,
    }


def main(argv:list[str]|None=None)->int:
    import argparse
    parser=argparse.ArgumentParser(
        description="Manual public GET-only deterministic Kalshi resolved-corpus capture"
    )
    parser.add_argument("--catalog-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--sample-size",type=int,default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument(
        "--max-trade-pages",type=int,default=DEFAULT_MAX_TRADE_PAGES
    )
    args=parser.parse_args(argv)
    try:
        result=capture_and_validate_kalshi_corpus(
            catalog_root=args.catalog_root,
            output_root=args.output,
            client=KalshiPublicResearchClient(),
            sample_size=args.sample_size,
            max_trade_pages=args.max_trade_pages,
        )
        print(json.dumps({
            "status":"KALSHI_RESOLVED_CORPUS_CAPTURE_AND_VALIDATION_COMPLETE",
            "sample_size":result["sample_size"],
            "manifest_sha256":result["manifest_sha256"],
            "credentials_accessed":"NONE",
            "network_methods":["GET"],
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
        },sort_keys=True,indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "status":"FAIL_CLOSED",
            "failure_class":type(exc).__name__,
            "credentials_accessed":"NONE",
            "network_methods":["GET"],
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
            "live_trading":"UNAVAILABLE",
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
