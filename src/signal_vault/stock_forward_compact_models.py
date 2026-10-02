"""Dependency-light two-model US-equity forward research runtime.

The frozen coefficients come from the exploratory public-data receipt at
research/models/phase162_public_github_stock_12h_models.json. That source's
market-data provenance is NOT independently verified, so this runtime is
strictly cross-source prospective shadow research on Signal Vault's own
verified Alpaca-IEX forward evidence.

No broker SDK, credentials, provider request, order draft, PAPER activation, or
live mode exists in this module.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from statistics import stdev
from typing import Mapping, Sequence

from .ci_historical_equities import SYMBOLS
from .ensemble_signals import ModelSignal, build_ensemble_opportunities
from .opportunity_engine import Market
from .research_universe import ResearchBar
from .signal_adapters import directional_model_signal

FEATURE_NAMES=(
    "r1","r3","r6","r12","r24","r48",
    "e6_18","e18_48","vol12","vol36","range","vz","rank24",
    "sym_AAPL","sym_AMD","sym_MSFT","sym_NVDA","sym_QQQ","sym_SPY",
)
MINIMUM_COMPLETED_CORE_HOURS=49
HORIZON_CORE_HOURS=12
BASE_ROUND_TRIP_COST_RETURN=Decimal("0.0013")
STRUCTURAL_MODEL_WEIGHT=Decimal("0.60")
MODEL_RECEIPT_PATH="research/models/phase162_public_github_stock_12h_models.json"


@dataclass(frozen=True)
class FrozenStockLinearModel:
    name:str
    threshold_abs_return:float
    intercept:float
    coef:tuple[float,...]
    mean:tuple[float,...]
    scale:tuple[float,...]

    def __post_init__(self)->None:
        width=len(FEATURE_NAMES)
        if not (
            len(self.coef)==width
            and len(self.mean)==width
            and len(self.scale)==width
        ):
            raise ValueError("stock model width differs from feature contract")
        if any(
            not math.isfinite(value)
            for value in (
                self.threshold_abs_return,self.intercept,
                *self.coef,*self.mean,*self.scale,
            )
        ):
            raise ValueError("stock model contains nonfinite values")
        if self.threshold_abs_return<=0 or any(x<=0 for x in self.scale):
            raise ValueError("invalid stock model threshold/scaler")

    def predict(self,vector:Sequence[float])->float:
        if len(vector)!=len(FEATURE_NAMES):
            raise ValueError("stock feature vector width mismatch")
        result=self.intercept
        for raw,mean,scale,weight in zip(
            vector,self.mean,self.scale,self.coef
        ):
            value=float(raw)
            if not math.isfinite(value):
                raise ValueError("nonfinite stock forward feature")
            result+=weight*((value-mean)/scale)
        if not math.isfinite(result):
            raise ValueError("nonfinite stock model prediction")
        return result


RIDGE10=FrozenStockLinearModel(
    "ridge10",0.003,0.000902140730099287,
    (
        -0.0012464424480481274,-0.0000012824001239235398,
        0.002722947610795618,0.003439491244470187,
        -0.0006270403656617769,-0.007514190121892145,
        -0.006690541313077831,0.007351818862621853,
        0.0023085156720786567,0.0006931121456715382,
        -0.00040457008580176563,0.0005868873769710429,
        0.0002943815636267617,0.00046891616354008495,
        0.0012370184536120022,-0.0018217423720415058,
        -0.00035334061231920077,0.00015176203797924125,
        0.0003173863292866289,
    ),
    (
        0.0000620178205725456,0.00016016790164843055,
        0.0003071094212572417,0.0007163069607977636,
        0.0014519616843980214,0.0021843883382428237,
        0.00004399730264808022,0.00006963808877536038,
        0.007136605118572587,0.007602538254610122,
        0.007003076040679455,0.00829363590773705,
        7.788613165697445e-18,
        1/6,1/6,1/6,1/6,1/6,1/6,
    ),
    (
        0.00976183564456006,0.016553329964063373,
        0.022773085680778887,0.031644114045501714,
        0.04459223290150356,0.061437039577846596,
        0.010833119027265534,0.015316690707638003,
        0.006700823883676706,0.006131794195489732,
        0.005448017582679472,1.0096955475165326,
        0.6831300510639604,
        0.3726779962500235,0.37267799625001247,
        0.3726779962500015,0.37267799624999026,
        0.37267799624997766,0.3726779962499651,
    ),
)

ROBUST_IRLS=FrozenStockLinearModel(
    "robust_irls_v1",0.005,0.0004801493336178558,
    (
        -0.0006588772649171801,0.00019845665684278612,
        0.0026604230532566537,0.0021360475944442476,
        -0.0008871610348483349,-0.005093164511914847,
        -0.006504613377659342,0.005417029913587033,
        0.0019365810562339482,0.0006778083483804293,
        0.000038161222284875385,0.000311392104658939,
        0.0008259686295480088,0.0003260952760312512,
        0.0003747564292140411,-0.0013208504676471534,
        -0.00015486578240908155,0.00030778572435091777,
        0.00047934169050246406,
    ),
    (
        0.000014337971379494977,-0.00001316131365482563,
        0.00003633882986547606,0.0005534852781777744,
        0.001025149252320945,0.0013785992389823251,
        -0.0000010667607970085566,-0.00011075019368652694,
        0.006629669493037402,0.0070868031903327435,
        0.0066422346359535,0.0017232578311642524,
        -0.004650337438650669,
        0.17338782526853655,0.1357312923249248,
        0.17193817635732794,0.15754779006563038,
        0.17968529708478528,0.18170961889879447,
    ),
    (
        0.009065213156549654,0.014964835045479324,
        0.02065118834917302,0.02873667046023467,
        0.04041780831056841,0.056376047889012376,
        0.009734919392370924,0.014098411747536132,
        0.005801927458978169,0.005482011863853316,
        0.005161219689532798,1.0070813505108487,
        0.6703032760564285,
        0.3785822068153387,0.3425030052550538,
        0.377326701769495,0.36431646121340144,
        0.3839251113125198,0.38560502239784783,
    ),
)
FROZEN_STOCK_MODELS=(RIDGE10,ROBUST_IRLS)


def _ret(values:Sequence[float],hours:int)->float:
    return values[-1]/values[-1-hours]-1.0


def _ema_last(values:Sequence[float],span:int)->float:
    alpha=2.0/(span+1.0)
    result=float(values[0])
    for raw in values[1:]:
        result=alpha*float(raw)+(1.0-alpha)*result
    return result


def _std(values:Sequence[float])->float:
    if len(values)<2:
        raise ValueError("stock rolling standard deviation needs two values")
    value=float(stdev(values))
    if not math.isfinite(value):
        raise ValueError("nonfinite stock rolling standard deviation")
    return value


def latest_stock_feature_vectors(
    datasets:Mapping[str,Sequence[ResearchBar]],
    *,
    allow_historical_warmup:bool=False,
)->tuple[dict[str,tuple[float,...]],datetime]:
    if set(datasets)!=set(SYMBOLS):
        raise ValueError("exact six-stock universe required")
    reference=None
    parts:dict[str,dict[str,float]]={}
    closes_at=set()
    for symbol in SYMBOLS:
        rows=tuple(datasets[symbol])
        if len(rows)<MINIMUM_COMPLETED_CORE_HOURS:
            raise ValueError("49 completed stock core hours required")
        if any(
            not isinstance(row,ResearchBar)
            or row.symbol!=symbol
            or row.feed!="alpaca_equity_iex|adjustment=all"
            for row in rows
        ):
            raise ValueError("stock feature input lacks verified IEX provenance")
        flags=tuple(row.prospective for row in rows)
        if allow_historical_warmup:
            if any(type(flag) is not bool for flag in flags):
                raise ValueError("stock warmup provenance flag must be boolean")
            first_prospective=next(
                (idx for idx,flag in enumerate(flags) if flag),
                len(flags),
            )
            if any(flags[:first_prospective]) or any(
                not flag for flag in flags[first_prospective:]
            ):
                raise ValueError("stock warmup must be historical prefix then prospective suffix")
            if first_prospective==len(flags):
                raise ValueError("stock model snapshot needs at least one prospective row")
        elif any(flag is not True for flag in flags):
            raise ValueError("stock feature input must be fully prospective")
        starts=tuple(row.start_utc for row in rows)
        if reference is None:
            reference=starts
        elif starts!=reference:
            raise ValueError("stock feature histories must share exact core-hour grid")

        close=[float(row.close) for row in rows]
        high=[float(row.high) for row in rows]
        low=[float(row.low) for row in rows]
        volume=[float(row.volume) for row in rows]
        returns36=[
            close[index]/close[index-1]-1.0
            for index in range(len(close)-36,len(close))
        ]
        vwin=volume[-18:]
        vstd=_std(vwin)
        vmean=sum(vwin)/len(vwin)
        e6=_ema_last(close,6)
        e18=_ema_last(close,18)
        e48=_ema_last(close,48)
        parts[symbol]={
            "r1":_ret(close,1),"r3":_ret(close,3),
            "r6":_ret(close,6),"r12":_ret(close,12),
            "r24":_ret(close,24),"r48":_ret(close,48),
            "e6_18":e6/e18-1.0,
            "e18_48":e18/e48-1.0,
            "vol12":_std(returns36[-12:]),
            "vol36":_std(returns36),
            "range":(high[-1]-low[-1])/close[-1],
            "vz":0.0 if vstd==0 else (volume[-1]-vmean)/vstd,
        }
        closes_at.add(rows[-1].closed_utc.astimezone(timezone.utc))

    if len(closes_at)!=1:
        raise ValueError("latest stock bars are not clock aligned")
    ordered=sorted(
        SYMBOLS,
        key=lambda symbol:(parts[symbol]["r24"],symbol),
    )
    for symbol in SYMBOLS:
        parts[symbol]["rank24"]=(
            ordered.index(symbol)/(len(SYMBOLS)-1)*2.0-1.0
        )

    vectors={}
    for symbol in SYMBOLS:
        core=[
            parts[symbol][name]
            for name in FEATURE_NAMES[:13]
        ]
        one_hot=[
            1.0 if symbol==candidate else 0.0
            for candidate in SYMBOLS
        ]
        vector=tuple(float(x) for x in (*core,*one_hot))
        if not all(math.isfinite(x) for x in vector):
            raise ValueError("nonfinite stock feature vector")
        vectors[symbol]=vector
    return vectors,next(iter(closes_at))


def _evidence(
    *,
    model:FrozenStockLinearModel,
    symbol:str,
    prediction:float,
    feature_close:datetime,
)->str:
    body={
        "model":model.name,
        "receipt":MODEL_RECEIPT_PATH,
        "symbol":symbol,
        "prediction":format(prediction,".17g"),
        "threshold":format(model.threshold_abs_return,".17g"),
        "feature_close":feature_close.isoformat(),
    }
    return "phase162-stock-xsource-sha256:"+hashlib.sha256(
        json.dumps(body,sort_keys=True,separators=(",",":")).encode()
    ).hexdigest()


def build_stock_cross_source_signals(
    datasets:Mapping[str,Sequence[ResearchBar]],
    *,
    captured_utc:datetime,
    allow_historical_warmup:bool=False,
)->tuple[ModelSignal,...]:
    if captured_utc.tzinfo is None or captured_utc.utcoffset() is None:
        raise ValueError("timezone-aware stock inference timestamp required")
    captured=captured_utc.astimezone(timezone.utc)
    vectors,feature_close=latest_stock_feature_vectors(
        datasets,
        allow_historical_warmup=allow_historical_warmup,
    )
    expiry=captured+timedelta(hours=1)
    output=[]
    for model in FROZEN_STOCK_MODELS:
        for symbol,vector in vectors.items():
            prediction=model.predict(vector)
            if abs(prediction)<model.threshold_abs_return:
                continue
            if abs(Decimal(format(prediction,".17g")))-BASE_ROUND_TRIP_COST_RETURN<=0:
                continue
            item=directional_model_signal(
                market=Market.US_EQUITY,
                instrument=symbol,
                source_model=model.name,
                strategy_family="phase162_publicdata_12h_cross_source_shadow",
                predicted_signed_return=Decimal(format(prediction,".17g")),
                estimated_round_trip_cost_return=BASE_ROUND_TRIP_COST_RETURN,
                confidence=STRUCTURAL_MODEL_WEIGHT,
                max_loss_return=Decimal("0.05"),
                generated_utc=captured,
                valid_until_utc=expiry,
                horizon_seconds=HORIZON_CORE_HOURS*3600,
                evidence_id=_evidence(
                    model=model,symbol=symbol,prediction=prediction,
                    feature_close=feature_close,
                ),
                correlation_group="us-equity-beta",
                paper_long_supported=False,
                paper_short_supported=False,
            )
            if item is not None:
                output.append(item)
    return tuple(output)


def stock_cross_source_ensemble_snapshot(
    datasets:Mapping[str,Sequence[ResearchBar]],
    *,
    captured_utc:datetime,
    allow_historical_warmup:bool=False,
)->dict[str,object]:
    signals=build_stock_cross_source_signals(
        datasets,
        captured_utc=captured_utc,
        allow_historical_warmup=allow_historical_warmup,
    )
    ensemble=build_ensemble_opportunities(
        signals,
        as_of=captured_utc,
        min_independent_models=2,
        min_consensus=Decimal("0.60"),
        min_expected_net_return=Decimal("0.001"),
    )
    return {
        "kind":"PHASE162_STOCK_CROSS_SOURCE_ENSEMBLE_NO_ORDER",
        "source_model_training_data_provenance_verified":False,
        "forward_evidence_provenance":"verified Alpaca IEX core hours",
        "historical_feature_warmup_used":allow_historical_warmup,
        "historical_feature_warmup_counts_as_prospective":False,
        "model_signal_count":len(signals),
        "opportunity_count":len(ensemble.opportunities),
        "opportunities":[{
            "instrument":item.instrument,
            "direction":item.direction.value,
            "component_models":list(item.component_models),
            "ensemble_consensus":str(item.ensemble_consensus),
            "expected_net_return":str(item.expected_net_return),
            "paper_executable":item.paper_executable,
        } for item in ensemble.opportunities],
        "rejected_groups":list(ensemble.rejected_groups),
        "paper_activation_permitted":False,
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
