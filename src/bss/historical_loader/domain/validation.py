"""Validation orchestration — aggregates duplicate/gap/ordering checks (ЧТЗ §10, AC-02..06)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .dataset import CandleBatch
from .duplicate_detector import DuplicateDetector, DuplicateInfo
from .gap_detector import Gap, GapDetector


@dataclass(frozen=True)
class ValidationIssue:
    """Structured validation issue with diagnostic context (08_RULES §7)."""

    code: str  # e.g. DUPLICATE, GAP, EMPTY_BATCH, MISMATCHED_SYMBOL, ORDERING
    message: str
    context: dict


@dataclass(frozen=True)
class ValidationResult:
    """Aggregate result of batch validation. Pure value object."""

    is_valid: bool
    issues: Tuple[ValidationIssue, ...]
    gaps: Tuple[Gap, ...]
    duplicates: Tuple[DuplicateInfo, ...]

    @property
    def has_gaps(self) -> bool:
        return len(self.gaps) > 0

    @property
    def has_duplicates(self) -> bool:
        return len(self.duplicates) > 0


class CandleValidator:
    """Pure validator that checks CandleBatch and produces ValidationResult.

    Does not mutate Raw, does not perform I/O, deterministic.
    """

    def __init__(
        self,
        duplicate_detector: DuplicateDetector | None = None,
        gap_detector: GapDetector | None = None,
    ) -> None:
        self._dup = duplicate_detector or DuplicateDetector()
        self._gap = gap_detector or GapDetector()

    def validate(self, batch: CandleBatch) -> ValidationResult:
        issues: list[ValidationIssue] = []

        # empty batch handling (ЧТЗ §10 — missing candles)
        if batch.is_empty:
            issues.append(
                ValidationIssue(
                    code="EMPTY_BATCH",
                    message="batch contains no candles",
                    context={"symbol": batch.symbol, "timeframe": batch.timeframe.value, "requested_range": [batch.requested_range.start.isoformat(), batch.requested_range.end.isoformat()]},
                )
            )

        # duplicates
        dups = self._dup.find_duplicates(batch)
        for d in dups:
            issues.append(
                ValidationIssue(
                    code="DUPLICATE",
                    message=f"duplicate candle_id {d.candle_id} count={d.count}",
                    context={"candle_id": d.candle_id, "open_time": d.open_time, "symbol": d.symbol, "timeframe": d.timeframe, "count": d.count},
                )
            )

        # gaps
        gaps = self._gap.find_gaps(batch)
        for g in gaps:
            issues.append(
                ValidationIssue(
                    code="GAP",
                    message=f"gap {g.missing_from.isoformat()}->{g.missing_to.isoformat()} expected {g.expected_candles} actual {g.actual_candles}",
                    context={"symbol": g.symbol, "timeframe": g.timeframe, "from": g.missing_from.isoformat(), "to": g.missing_to.isoformat(), "expected": g.expected_candles, "actual": g.actual_candles},
                )
            )

        # Candle-level OHLC/timestamp already validated by Candle; here we just check ordering is still sorted
        # CandleBatch already enforces sorted, but if batch was constructed bypassing, we double-check
        for i in range(1, len(batch.candles)):
            if batch.candles[i - 1].open_time >= batch.candles[i].open_time:
                issues.append(
                    ValidationIssue(
                        code="ORDERING",
                        message="candles not strictly ordered by open_time",
                        context={"index": i, "prev": batch.candles[i - 1].open_time.isoformat(), "curr": batch.candles[i].open_time.isoformat()},
                    )
                )
                break

        is_valid = len(issues) == 0
        return ValidationResult(
            is_valid=is_valid,
            issues=tuple(issues),
            gaps=tuple(gaps),
            duplicates=tuple(dups),
        )
