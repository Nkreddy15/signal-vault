"""Leakage-resistant historical train/validation/test split planning.

The planner is market-agnostic about strategy choice. It only enforces chronology:
older observations train, later observations validate, and the newest block stays
untouched for final historical testing. Kalshi uses event order rather than hours.

No network access, optimization, model selection, or order submission occurs here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, TypeVar

T=TypeVar("T")


@dataclass(frozen=True)
class ChronologicalSplit:
    train_count:int
    validation_count:int
    test_count:int
    warmup_count:int

    def __post_init__(self)->None:
        values=(self.train_count,self.validation_count,self.test_count,self.warmup_count)
        if any(type(x) is not int or x<0 for x in values):
            raise ValueError("split counts must be nonnegative integers")
        if self.train_count<=0 or self.validation_count<=0 or self.test_count<=0:
            raise ValueError("train validation and test must all be nonempty")

    @property
    def total_count(self)->int:
        return self.warmup_count+self.train_count+self.validation_count+self.test_count


def chronological_split(
    observations:Sequence[T],
    *,
    warmup_count:int=0,
    train_fraction:float=0.60,
    validation_fraction:float=0.20,
)->dict[str,object]:
    items=tuple(observations)
    if type(warmup_count) is not int or warmup_count<0:
        raise ValueError("invalid warmup count")
    if not 0.5<=train_fraction<0.9:
        raise ValueError("train fraction outside conservative range")
    if not 0.1<=validation_fraction<=0.3:
        raise ValueError("validation fraction outside conservative range")
    usable=len(items)-warmup_count
    if usable<15:
        raise ValueError("historical dataset too small for three-way chronology")
    train=int(usable*train_fraction)
    validation=int(usable*validation_fraction)
    test=usable-train-validation
    split=ChronologicalSplit(train,validation,test,warmup_count)
    if split.total_count!=len(items):
        raise AssertionError("split does not cover source exactly")
    a=warmup_count
    b=a+train
    c=b+validation
    return {
        "kind":"CHRONOLOGICAL_HISTORICAL_SPLIT_NOT_FORWARD_EVIDENCE",
        "warmup":items[:a],
        "train":items[a:b],
        "validation":items[b:c],
        "untouched_test":items[c:],
        "counts":{
            "warmup":warmup_count,
            "train":train,
            "validation":validation,
            "untouched_test":test,
            "total":len(items),
        },
        "strictly_chronological":True,
        "test_period_used_for_strategy_selection":False,
        "historical_data_is_not_prospective_validation":True,
        "broker_order_submission":"DISABLED",
    }


def expanding_walk_forward(
    observations:Sequence[T],
    *,
    initial_train_count:int,
    validation_count:int,
    step_count:int,
)->tuple[dict[str,object],...]:
    items=tuple(observations)
    for value in (initial_train_count,validation_count,step_count):
        if type(value) is not int or value<=0:
            raise ValueError("walk-forward counts must be positive integers")
    if initial_train_count<10 or validation_count<2:
        raise ValueError("walk-forward windows are too small")
    output=[]
    train_end=initial_train_count
    fold=1
    while train_end+validation_count<=len(items):
        valid_end=train_end+validation_count
        output.append({
            "fold":fold,
            "train":items[:train_end],
            "validation":items[train_end:valid_end],
            "train_count":train_end,
            "validation_count":validation_count,
            "strictly_past_trains_future_validation":True,
        })
        train_end+=step_count
        fold+=1
    if not output:
        raise ValueError("not enough observations for one walk-forward fold")
    return tuple(output)


def market_validation_contract(
    *,
    market_lane:str,
    observation_count:int,
    split:dict[str,object],
    walk_forward_fold_count:int,
)->dict[str,object]:
    if market_lane not in {"crypto","us_equity","kalshi_event_contract"}:
        raise ValueError("unsupported market lane")
    if type(observation_count) is not int or observation_count<=0:
        raise ValueError("positive observation count required")
    if split.get("counts",{}).get("total")!=observation_count:
        raise ValueError("split/source observation count mismatch")
    if type(walk_forward_fold_count) is not int or walk_forward_fold_count<=0:
        raise ValueError("at least one walk-forward fold required")
    return {
        "kind":"MARKET_HISTORICAL_VALIDATION_CONTRACT_NOT_LIVE_AUTHORIZATION",
        "market_lane":market_lane,
        "historical_observation_count":observation_count,
        "walk_forward_fold_count":walk_forward_fold_count,
        "untouched_test_reserved":True,
        "historical_validation_complete":False,
        "requires_separate_prospective_or_paper_validation":True,
        "automatic_strategy_promotion":"DISABLED",
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
