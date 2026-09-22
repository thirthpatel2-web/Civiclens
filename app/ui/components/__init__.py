"""Reusable, theme-aware building blocks shared across every CivicLens screen.

These sit on top of ``app.ui.theme`` (tokens/CSS) and ``app.ui.base`` (session, translation, the
``badge``/``empty_state``/``stat_card`` primitives). Anything that was being re-implemented slightly
differently on three or four pages belongs here instead, so the product reads as one system rather
than a collection of independently styled screens.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import contextmanager
from typing import Any

from nicegui import run, ui


async def run_with_loading(btn: Any, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a blocking call off the event loop while ``btn`` shows a spinner and is disabled.

    Without this, a synchronous handler (e.g. Argon2 password verification) blocks the whole
    NiceGUI event loop, so the "loading" prop we set never actually reaches the browser before
    the work finishes - the button would look inert rather than busy. Awaiting the call via
    ``run.io_bound`` yields control back to the loop first, so the spinner really shows.
    """
    btn.props("loading")
    btn.disable()
    try:
        return await run.io_bound(fn, *args, **kwargs)
    finally:
        btn.props(remove="loading")
        btn.enable()


def page_header(title: str, subtitle: str | None = None, *, icon: str | None = None, actions: Callable[[], None] | None = None) -> None:
    """Title + optional subtitle + optional right-aligned action(s), used at the top of every page."""
    with ui.row().classes("w-full items-start justify-between gap-4 flex-wrap"):
        with ui.row().classes("items-center gap-3"):
            if icon:
                with ui.element("div").classes("cl-stat-icon bg-primary-soft").style("background: var(--cl-primary-soft); color: var(--cl-primary);"):
                    ui.icon(icon).classes("text-[20px]")
            with ui.column().classes("gap-0"):
                ui.label(title).classes("text-xl font-semibold cl-title").style("color: var(--cl-fg);")
                if subtitle:
                    ui.label(subtitle).classes("text-sm").style("color: var(--cl-fg-muted); max-width: 60ch;")
        if actions:
            with ui.row().classes("gap-2 items-center"):
                actions()


def section_title(title: str, subtitle: str | None = None) -> None:
    with ui.column().classes("gap-0 w-full"):
        ui.label(title).classes("text-sm font-semibold uppercase").style("color: var(--cl-fg-muted); letter-spacing: .06em;")
        if subtitle:
            ui.label(subtitle).classes("text-xs").style("color: var(--cl-fg-subtle);")


@contextmanager
def surface(*, padded: bool = True, hover: bool = False, flat: bool = False):
    """A themed card container. Use as ``with surface(): ...``."""
    cls = "cl-card-flat" if flat else "cl-card"
    if hover:
        cls += " cl-card-hover"
    if not padded:
        cls += " !p-0"
    with ui.column().classes(f"{cls} w-full gap-2") as col:
        yield col


def stat_tile(label: str, value: Any, *, color: str = "primary", icon: str | None = None, hint: str | None = None, trend: str | None = None) -> None:
    """Dashboard KPI tile: icon chip + big number + label + optional hint/trend line."""
    with ui.column().classes("cl-card cl-stat gap-1"):
        with ui.row().classes("items-center justify-between w-full"):
            ui.label(label).classes("text-xs font-medium").style("color: var(--cl-fg-muted);")
            if icon:
                with ui.element("div").classes("cl-stat-icon").style(f"background: var(--cl-{color}-soft); color: var(--cl-{color});"):
                    ui.icon(icon).classes("text-[18px]")
        ui.label(str(value)).classes("text-2xl font-bold").style("color: var(--cl-fg); letter-spacing: -.02em;")
        if hint or trend:
            ui.label(trend or hint).classes("text-xs").style("color: var(--cl-fg-subtle);")


def chip(text: str, *, color: str = "muted", icon: str | None = None, outline: bool = False) -> None:
    cls = "cl-badge " + ("cl-badge-outline" if outline else f"cl-badge-{color}")
    with ui.row().classes(cls):
        if icon:
            ui.icon(icon)
        ui.label(text)


def dot_label(text: str, *, color: str = "muted") -> None:
    with ui.row().classes("items-center gap-2"):
        ui.element("span").classes(f"cl-dot cl-dot-{color}")
        ui.label(text).classes("text-sm").style("color: var(--cl-fg);")


def skeleton_lines(n: int = 3, *, widths: Iterable[str] = ("100%", "88%", "64%")) -> None:
    ws = list(widths)
    with ui.column().classes("w-full gap-2"):
        for i in range(n):
            w = ws[i % len(ws)]
            ui.element("div").classes("cl-skeleton").style(f"height: 14px; width: {w};")


def skeleton_cards(n: int = 3) -> None:
    with ui.row().classes("gap-3 w-full flex-wrap"):
        for _ in range(n):
            with ui.column().classes("cl-card cl-stat gap-2"):
                ui.element("div").classes("cl-skeleton").style("height: 12px; width: 60%;")
                ui.element("div").classes("cl-skeleton").style("height: 22px; width: 40%;")


def state_panel(*, icon: str, title: str, body: str | None = None, action_label: str | None = None, on_action: Callable[[], None] | None = None, tone: str = "muted") -> None:
    """One consistent shape for empty / error / unavailable / permission-denied states."""
    with ui.column().classes("cl-state"):
        ui.icon(icon).style(f"color: var(--cl-{tone});" if tone != "muted" else None)
        ui.label(title).classes("cl-state-title")
        if body:
            ui.label(body).classes("cl-state-body")
        if action_label and on_action:
            ui.button(action_label, on_click=on_action).props("outline unelevated").classes("q-mt-sm")


def status_timeline(steps: list[Any]) -> None:
    """Vertical progress timeline. ``steps`` items need ``.label``, ``.state`` and ``.at`` (or falls back to state text)."""
    icon_for = {"done": "check", "current": "radio_button_checked", "upcoming": "radio_button_unchecked", "skipped": "remove", "rejected": "close"}
    cls_for = {"done": "cl-done", "current": "cl-current", "upcoming": "", "skipped": "", "rejected": "cl-rejected"}
    with ui.column().classes("cl-timeline w-full gap-0"):
        for s in steps:
            with ui.column().classes("cl-timeline-step gap-0"):
                with ui.element("div").classes(f"cl-timeline-dot {cls_for.get(s.state, '')}"):
                    ui.icon(icon_for.get(s.state, "circle"))
                ui.label(s.label).classes("text-sm font-medium").style("color: var(--cl-fg);")
                when = s.at.strftime("%d %b %Y, %H:%M") if getattr(s, "at", None) else s.state.replace("_", " ").title()
                ui.label(when).classes("text-xs").style("color: var(--cl-fg-subtle);")


def steps_bar(labels: list[str], current: int) -> None:
    """Horizontal numbered stepper used by multi-section forms (Report, RTI)."""
    with ui.row().classes("cl-steps"):
        for i, label in enumerate(labels):
            state = "cl-done" if i < current else ("cl-active" if i == current else "")
            with ui.row().classes(f"cl-step {state}"):
                with ui.element("div").classes("cl-step-num"):
                    ui.label("✓" if i < current else str(i + 1))
                ui.label(label).classes("cl-step-label")
            if i < len(labels) - 1:
                ui.element("div").classes("cl-step-sep")


def chat_bubble(text: str, *, is_user: bool) -> None:
    row_cls = "cl-chat-row " + ("cl-user" if is_user else "cl-assistant")
    with ui.row().classes(row_cls):
        if not is_user:
            with ui.element("div").classes("cl-chat-avatar q-mr-sm"):
                ui.icon("auto_awesome").classes("text-[16px]")
        with ui.element("div").classes("cl-chat-bubble"):
            ui.label(text).style("white-space: pre-wrap; color: inherit;")


def field_hint(text: str) -> None:
    ui.label(text).classes("text-xs q-mb-xs").style("color: var(--cl-fg-subtle);")


def divider() -> None:
    ui.separator().classes("cl-divider")


def confirm_dialog(title: str, body: str, *, confirm_label: str = "Confirm", cancel_label: str = "Cancel", danger: bool = False, on_confirm: Callable[[], None]) -> Callable[[], None]:
    """Build a confirmation dialog once; returns a function that opens it. Prevents accidental destructive taps.

    This module is deliberately container-free, so both button labels are passed in already
    translated by the caller rather than looked up here.
    """
    with ui.dialog() as dlg, ui.column().classes("cl-card gap-3 w-full max-w-sm"):
        ui.label(title).classes("text-base font-semibold")
        ui.label(body).classes("text-sm").style("color: var(--cl-fg-muted);")
        with ui.row().classes("justify-end gap-2 w-full q-mt-sm"):
            ui.button(cancel_label, on_click=dlg.close).props("flat")

            def go() -> None:
                dlg.close()
                on_confirm()

            ui.button(confirm_label, on_click=go).props(f"unelevated color={'negative' if danger else 'primary'}")
    return dlg.open
