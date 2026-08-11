from datetime import UTC, datetime
from decimal import Decimal

from app.domain.quotes.entities import Quote
from app.domain.quotes.exceptions import InvalidQuoteState
from app.domain.quotes.value_objects import QuoteStatus


def _now() -> datetime:
    return datetime.now(UTC)


def _transition(quote: Quote, target: QuoteStatus, allowed: set[QuoteStatus]) -> None:
    if quote.status is target:
        return
    if quote.status not in allowed:
        raise InvalidQuoteState(
            f"Quote cannot transition from {quote.status.value} to {target.value}."
        )
    quote.status = target
    quote.updated_at = _now()


def mark_ready_for_analysis(quote: Quote) -> None:
    _transition(
        quote,
        QuoteStatus.READY_FOR_ANALYSIS,
        {QuoteStatus.RECEIVED, QuoteStatus.VALIDATING},
    )
    quote.last_error = None


def start_analysis(quote: Quote) -> None:
    if quote.status is QuoteStatus.VALIDATING:
        mark_ready_for_analysis(quote)
    _transition(quote, QuoteStatus.ANALYZING, {QuoteStatus.READY_FOR_ANALYSIS})
    quote.last_error = None


def mark_analyzed(quote: Quote) -> None:
    _transition(quote, QuoteStatus.ANALYZED, {QuoteStatus.ANALYZING})


def mark_pending_review(quote: Quote) -> None:
    _transition(quote, QuoteStatus.PENDING_REVIEW, {QuoteStatus.ANALYZED})


def restart_analysis(quote: Quote) -> None:
    if quote.status in {QuoteStatus.APPROVED, QuoteStatus.INCLUDED_IN_COMPARISON}:
        raise InvalidQuoteState("Approved quotes cannot be reanalyzed silently.")
    if quote.status not in {
        QuoteStatus.PENDING_REVIEW,
        QuoteStatus.REJECTED,
        QuoteStatus.FAILED,
        QuoteStatus.ANALYZED,
    }:
        raise InvalidQuoteState("Quote is not eligible for reanalysis.")
    quote.status = QuoteStatus.VALIDATING
    quote.updated_at = _now()
    quote.last_error = None
    mark_ready_for_analysis(quote)


def mark_analysis_failed(quote: Quote, error: Exception | str) -> None:
    if quote.status in {QuoteStatus.APPROVED, QuoteStatus.INCLUDED_IN_COMPARISON}:
        quote.record_error(error if isinstance(error, Exception) else RuntimeError(str(error)))
        return
    quote.status = QuoteStatus.FAILED
    quote.last_error = str(error)[:4000]
    quote.updated_at = _now()


def apply_analysis_summary(
    quote: Quote,
    *,
    currency: str | None,
    subtotal_amount: Decimal | None,
    tax_amount: Decimal | None,
    total_amount: Decimal | None,
    delivery_time_days: int | None,
    commercial_terms: str | None,
    valid_until: datetime | None,
) -> None:
    if quote.status is not QuoteStatus.ANALYZING:
        raise InvalidQuoteState("Quote summary can only be applied while analysis is running.")
    quote.currency = currency.strip().upper() if currency else None
    quote.subtotal_amount = subtotal_amount
    quote.tax_amount = tax_amount
    quote.total_amount = total_amount
    quote.delivery_time_days = delivery_time_days
    quote.commercial_terms = commercial_terms
    quote.valid_until = valid_until
    quote.updated_at = _now()
