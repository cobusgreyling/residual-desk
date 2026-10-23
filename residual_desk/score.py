"""Route one fixed call set through always-big, rules-then-big, and small-judge-then-big."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

POLICIES = ("always-big", "rules-then-big", "small-judge-then-big")
TIERS = ("rules", "small", "big")
ACTIONS = ("close", "pass")


@dataclass(frozen=True)
class Prices:
    rules: Decimal
    small: Decimal
    big: Decimal

    def for_tier(self, tier: str) -> Decimal:
        return getattr(self, tier)


@dataclass(frozen=True)
class Call:
    id: str
    title: str
    rules: str
    small: str
    big: str
    can_close: frozenset[str]

    def action(self, tier: str) -> str:
        return getattr(self, tier)


@dataclass(frozen=True)
class Route:
    policy: str
    call_id: str
    tier: str
    closed: bool
    cost: Decimal
    reason: str


@dataclass(frozen=True)
class Summary:
    policy: str
    closed: int
    total: int
    cost: Decimal


@dataclass(frozen=True)
class Report:
    path: str
    prices: Prices
    summaries: tuple[Summary, ...]
    routes: tuple[Route, ...]


def score_path(path: Path) -> Report:
    prices, calls = _load(path)
    routes = tuple(_route(policy, call, prices) for policy in POLICIES for call in calls)
    summaries = tuple(_summarize(policy, routes, len(calls)) for policy in POLICIES)
    return Report(path=str(path), prices=prices, summaries=summaries, routes=routes)


def format_table(report: Report) -> str:
    header = ("policy", "closed", "close rate", "cost USD")
    rows = [
        (
            summary.policy,
            f"{summary.closed}/{summary.total}",
            _percent(summary.closed, summary.total),
            _money(summary.cost),
        )
        for summary in report.summaries
    ]
    widths = [
        max(len(header[index]), *(len(row[index]) for row in rows))
        for index in range(4)
    ]

    def line(cells: tuple[str, ...]) -> str:
        parts = []
        for index, cell in enumerate(cells):
            parts.append(cell.ljust(widths[index]) if index == 0 else cell.rjust(widths[index]))
        return "  ".join(parts)

    body = [line(header), line(tuple("-" * width for width in widths))]
    body.extend(line(row) for row in rows)
    prices = report.prices
    note = (
        "Prices are illustrative: "
        f"rules {_money(prices.rules)}, small {_money(prices.small)}, "
        f"big {_money(prices.big)} USD per attempt."
    )
    return "\n".join(body) + "\n\n" + note


def format_details(report: Report) -> str:
    blocks: list[str] = []
    for policy in POLICIES:
        lines = [policy]
        opened = [route for route in report.routes if route.policy == policy and not route.closed]
        if not opened:
            lines.append("  none open")
        for route in opened:
            lines.append(f"  open  {route.call_id}  {route.tier}  {route.reason}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _route(policy: str, call: Call, prices: Prices) -> Route:
    if policy == "always-big":
        return _finish(policy, call, "big", prices.big)
    if policy == "rules-then-big":
        if call.rules == "close":
            return _finish(policy, call, "rules", prices.rules)
        return _finish(policy, call, "big", prices.rules + prices.big)
    if policy == "small-judge-then-big":
        if call.small == "close":
            return _finish(policy, call, "small", prices.small)
        return _finish(policy, call, "big", prices.small + prices.big)
    raise ValueError(f"unknown policy: {policy}")


def _finish(policy: str, call: Call, tier: str, cost: Decimal) -> Route:
    action = call.action(tier)
    if action == "close" and tier in call.can_close:
        closed, reason = True, "closed"
    elif action == "close":
        closed, reason = False, "false close"
    else:
        closed, reason = False, "passed"
    return Route(policy, call.id, tier, closed, cost, reason)


def _summarize(policy: str, routes: tuple[Route, ...], total: int) -> Summary:
    selected = [route for route in routes if route.policy == policy]
    return Summary(
        policy=policy,
        closed=sum(route.closed for route in selected),
        total=total,
        cost=sum((route.cost for route in selected), Decimal("0")),
    )


def _load(path: Path) -> tuple[Prices, tuple[Call, ...]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        raise
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"{path}: empty fixture")
    try:
        records = [json.loads(line) for line in lines]
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON") from exc
    if not records or not isinstance(records[0], dict):
        raise ValueError(f"{path}: first record must be type prices")
    prices = _prices(records[0], path)
    calls: list[Call] = []
    seen: set[str] = set()
    for record in records[1:]:
        call = _call(record, path)
        if call.id in seen:
            raise ValueError(f"{path}: duplicate call id {call.id}")
        seen.add(call.id)
        calls.append(call)
    if not calls:
        raise ValueError(f"{path}: no calls")
    return prices, tuple(calls)


def _prices(record: dict, path: Path) -> Prices:
    if record.get("type") != "prices":
        raise ValueError(f"{path}: first record must be type prices")
    if record.get("note") != "illustrative":
        raise ValueError(f"{path}: prices note must be illustrative")
    return Prices(
        rules=_amount(record.get("rules"), "rules", path),
        small=_amount(record.get("small"), "small", path),
        big=_amount(record.get("big"), "big", path),
    )


def _call(record: object, path: Path) -> Call:
    if not isinstance(record, dict) or record.get("type") != "call":
        raise ValueError(f"{path}: expected a call record")
    call_id = record.get("id")
    title = record.get("title")
    if not isinstance(call_id, str) or not call_id:
        raise ValueError(f"{path}: call id must be a string")
    if not isinstance(title, str) or not title:
        raise ValueError(f"{path}: call title must be a string")
    actions = {tier: _action(record.get(tier), tier, path) for tier in TIERS}
    can_close = _can_close(record.get("can_close"), path)
    return Call(call_id, title, can_close=can_close, **actions)


def _action(value: object, tier: str, path: Path) -> str:
    if value not in ACTIONS:
        raise ValueError(f"{path}: {tier} must be close or pass")
    return str(value)


def _can_close(value: object, path: Path) -> frozenset[str]:
    if not isinstance(value, list) or any(item not in TIERS for item in value):
        raise ValueError(f"{path}: can_close must list rules, small, or big")
    if len(value) != len(set(value)):
        raise ValueError(f"{path}: can_close has a duplicate tier")
    return frozenset(str(item) for item in value)


def _amount(value: object, name: str, path: Path) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{path}: {name} price must be a decimal string")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{path}: {name} price must be a decimal string") from exc
    if amount <= 0:
        raise ValueError(f"{path}: {name} price must be positive")
    return amount


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP):.3f}"


def _percent(closed: int, total: int) -> str:
    rate = (Decimal(closed) / Decimal(total) * Decimal(100)).quantize(
        Decimal("0.1"),
        rounding=ROUND_HALF_UP,
    )
    return f"{rate:.1f}%"
