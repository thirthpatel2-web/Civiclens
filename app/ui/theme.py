"""CivicLens design system: colour tokens (light + dark), typography, elevation and the global stylesheet.

Design tokens are plain hex custom properties on ``:root``. Dark mode does not invert them -
``body.body--dark`` (the class Quasar's Dark plugin toggles when ``ui.dark_mode()`` is switched)
redefines the same variable names with ``!important``, so every already-rendered element repaints
instantly with no page reload and no component needs to know which theme is active.

Status/priority/SLA colours below resolve to the *semantic* palette (success/warning/danger/info/ai/
muted), never to raw Quasar palette names, so a badge painted today looks right in both themes and if
the palette is retuned later every call site updates itself.
"""

from __future__ import annotations

FONT_STACK = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
FONT_MONO = "'JetBrains Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace"

# ---------------------------------------------------------------------------------------------
# Colour tokens
# ---------------------------------------------------------------------------------------------

LIGHT: dict[str, str] = {
    "bg": "#F5F7FA",
    "surface": "#FFFFFF",
    "surface-alt": "#EEF1F6",
    "surface-hover": "#E7EBF2",
    "fg": "#121826",
    "fg-muted": "#5B6472",
    "fg-subtle": "#8A93A3",
    "border": "#E2E6ED",
    "border-strong": "#C7CEDA",
    "primary": "#1E3A5F",
    "primary-strong": "#12233B",
    "primary-soft": "#E8EEF5",
    "primary-fg": "#FFFFFF",
    "secondary": "#0E7C86",
    "secondary-soft": "#E3F3F3",
    "success": "#1B8A57",
    "success-soft": "#E5F5EC",
    "warning": "#96630F",
    "warning-soft": "#FBF0DD",
    "danger": "#B3261E",
    "danger-soft": "#FBE8E7",
    "info": "#2563AA",
    "info-soft": "#E7F0FA",
    "ai": "#5B4FD6",
    "ai-soft": "#EFEDFC",
    "emergency": "#C22A1B",
    "emergency-soft": "#FBE7E4",
    "muted": "#667085",
    "muted-soft": "#EEF0F3",
    "sidebar": "#0F1B2E",
    "sidebar-fg": "#C7D0DE",
    "sidebar-fg-muted": "#8592A6",
    "sidebar-hover": "#182A45",
    "sidebar-active": "#1E3A5F",
    "sidebar-border": "rgba(255,255,255,0.08)",
    "glow-primary": "rgba(30,58,95,.38)",
    "glow-ai": "rgba(91,79,214,.32)",
    "glass-bg": "rgba(255,255,255,.66)",
    "glass-border": "rgba(255,255,255,.5)",
}

DARK: dict[str, str] = {
    "bg": "#0C121C",
    "surface": "#141C2B",
    "surface-alt": "#1B2536",
    "surface-hover": "#233047",
    "fg": "#E7EAF1",
    "fg-muted": "#9AA5B4",
    "fg-subtle": "#6B7688",
    "border": "rgba(255,255,255,0.09)",
    "border-strong": "rgba(255,255,255,0.17)",
    "primary": "#5F90C7",
    "primary-strong": "#7DA8D8",
    "primary-soft": "#1C2E45",
    "primary-fg": "#0A1220",
    "secondary": "#3FBAC2",
    "secondary-soft": "#123336",
    "success": "#49C48C",
    "success-soft": "#123626",
    "warning": "#E3AE49",
    "warning-soft": "#3A2C11",
    "danger": "#E5695D",
    "danger-soft": "#3B1D1A",
    "info": "#6BA8E0",
    "info-soft": "#152A3E",
    "ai": "#9A8CFF",
    "ai-soft": "#231F3F",
    "emergency": "#E5715F",
    "emergency-soft": "#3A1E19",
    "muted": "#8B96A8",
    "muted-soft": "#1D2635",
    "sidebar": "#080D16",
    "sidebar-fg": "#B7C1D1",
    "sidebar-fg-muted": "#6E7A8D",
    "sidebar-hover": "#131E30",
    "sidebar-active": "#20385A",
    "sidebar-border": "rgba(255,255,255,0.06)",
    "glow-primary": "rgba(95,144,199,.5)",
    "glow-ai": "rgba(154,140,255,.55)",
    "glass-bg": "rgba(20,28,43,.62)",
    "glass-border": "rgba(255,255,255,.10)",
}

RADIUS = {"xs": "6px", "sm": "8px", "md": "12px", "lg": "16px", "xl": "22px", "pill": "999px"}

SHADOW = {
    "light-soft": "0 1px 2px rgba(16,24,40,.05), 0 6px 16px -8px rgba(16,24,40,.12)",
    "light-lift": "0 2px 8px rgba(16,24,40,.08), 0 20px 36px -18px rgba(16,24,40,.22)",
    "dark-soft": "0 1px 2px rgba(0,0,0,.35), 0 6px 18px -8px rgba(0,0,0,.5)",
    "dark-lift": "0 2px 10px rgba(0,0,0,.4), 0 22px 40px -18px rgba(0,0,0,.6)",
}

# Back-compat surface used by a couple of legacy call sites that reference COLORS directly.
COLORS = {"primary": LIGHT["primary"], "accent": LIGHT["secondary"], "ok": LIGHT["success"], "warn": LIGHT["warning"], "bad": LIGHT["danger"], "muted": LIGHT["muted"], "surface": LIGHT["surface-alt"]}

# Passed to ``ui.colors(**QUASAR_COLOR_KWARGS)``. Must be called with these explicit light-mode
# values (never bare ``ui.colors()``): NiceGUI's colour element writes every prop it receives -
# including ones you didn't pass, using Quasar's stock defaults - as an *inline* style on <body>,
# which would silently outrank the ``:root`` palette defined in ``CSS`` above. Passing the same
# light values here keeps that inline write a no-op while still registering the custom colour names
# (ai/emergency/success/muted) with Quasar so `color="success"` works on any component's `color` prop.
QUASAR_COLOR_KWARGS = {
    "primary": LIGHT["primary"], "secondary": LIGHT["secondary"], "accent": LIGHT["secondary"],
    "dark": LIGHT["surface"], "dark_page": LIGHT["bg"],
    "positive": LIGHT["success"], "negative": LIGHT["danger"], "info": LIGHT["info"], "warning": LIGHT["warning"],
    "success": LIGHT["success"], "ai": LIGHT["ai"], "emergency": LIGHT["emergency"], "muted": LIGHT["muted"],
}

STATUS_COLOR = {
    "submitted": "muted",
    "ai_routed": "info",
    "assigned": "primary",
    "under_review": "warning",
    "inspection_scheduled": "ai",
    "in_progress": "info",
    "resolved": "success",
    "closed": "success",
    "rejected": "danger",
}
PRIORITY_COLOR = {"low": "muted", "medium": "info", "high": "warning", "critical": "danger"}
SLA_COLOR = {"on_track": "success", "at_risk": "warning", "breached": "danger", "no_policy": "muted", "finished": "muted"}

STATUS_ICON = {
    "submitted": "inbox",
    "ai_routed": "route",
    "assigned": "assignment_ind",
    "under_review": "search",
    "inspection_scheduled": "event_available",
    "in_progress": "engineering",
    "resolved": "task_alt",
    "closed": "check_circle",
    "rejected": "cancel",
}


def _vars(tokens: dict[str, str], *, important: bool = False) -> str:
    bang = " !important" if important else ""
    lines = [f"  --cl-{name}: {value}{bang};" for name, value in tokens.items()]
    return "\n".join(lines)


def _quasar_colors(mode: str) -> str:
    t = LIGHT if mode == "light" else DARK
    bang = " !important" if mode == "dark" else ""
    pairs = {
        "primary": t["primary"], "secondary": t["secondary"], "accent": t["secondary"],
        "positive": t["success"], "negative": t["danger"], "info": t["info"], "warning": t["warning"],
        "dark": t["surface"], "dark-page": t["bg"],
        "success": t["success"], "ai": t["ai"], "emergency": t["emergency"], "muted": t["muted"],
    }
    return "\n".join(f"  --q-{name}: {value}{bang};" for name, value in pairs.items())


FONT_IMPORT = "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');"

CSS = f"""
{FONT_IMPORT}
:root {{
{_vars(LIGHT)}
  --cl-radius-xs: {RADIUS["xs"]}; --cl-radius-sm: {RADIUS["sm"]}; --cl-radius-md: {RADIUS["md"]};
  --cl-radius-lg: {RADIUS["lg"]}; --cl-radius-xl: {RADIUS["xl"]}; --cl-radius-pill: {RADIUS["pill"]};
  --cl-shadow-soft: {SHADOW["light-soft"]};
  --cl-shadow-lift: {SHADOW["light-lift"]};
  --cl-font: {FONT_STACK};
  --cl-font-mono: {FONT_MONO};
  --cl-gradient-brand: linear-gradient(135deg, var(--cl-primary-strong) 0%, var(--cl-primary) 45%, var(--cl-ai) 100%);
  --cl-gradient-ai: linear-gradient(135deg, var(--cl-ai) 0%, var(--cl-secondary) 100%);
  --cl-gradient-mesh-1: var(--cl-primary);
  --cl-gradient-mesh-2: var(--cl-ai);
  --cl-gradient-mesh-3: var(--cl-secondary);
{_quasar_colors("light")}
}}

body.body--dark {{
{_vars(DARK, important=True)}
  --cl-shadow-soft: {SHADOW["dark-soft"]} !important;
  --cl-shadow-lift: {SHADOW["dark-lift"]} !important;
{_quasar_colors("dark")}
}}

/* ---- base ------------------------------------------------------------------------------- */
* {{ box-sizing: border-box; }}
html, body {{ background: var(--cl-bg); }}
body {{
  background: var(--cl-bg) !important;
  color: var(--cl-fg) !important;
  font-family: var(--cl-font);
  -webkit-font-smoothing: antialiased;
  transition: background-color .16s ease, color .16s ease;
}}
.q-page {{ background: var(--cl-bg); }}
a {{ color: var(--cl-primary); }}
::selection {{ background: var(--cl-primary-soft); color: var(--cl-primary-strong); }}
.cl-mono {{ font-family: var(--cl-font-mono); }}

/* visible, high-contrast focus ring for keyboard users everywhere */
.cl-focusable:focus-visible, button:focus-visible, a:focus-visible, [tabindex]:focus-visible {{
  outline: 2px solid var(--cl-info); outline-offset: 2px; border-radius: var(--cl-radius-xs);
}}
.cl-skip-link {{
  position: fixed; top: -48px; left: 12px; z-index: 4000; background: var(--cl-surface); color: var(--cl-fg);
  padding: 10px 16px; border-radius: var(--cl-radius-sm); box-shadow: var(--cl-shadow-lift); transition: top .15s ease;
}}
.cl-skip-link:focus {{ top: 12px; }}

/* ---- layout shell ------------------------------------------------------------------------ */
.cl-page {{ max-width: 1280px; margin: 0 auto; width: 100%; }}
.cl-page-narrow {{ max-width: 880px; margin: 0 auto; width: 100%; }}
.cl-shell-header {{
  background: var(--cl-surface) !important; color: var(--cl-fg) !important;
  border-bottom: 1px solid var(--cl-border); position: relative;
}}
.cl-shell-header::after {{ content: ""; position: absolute; left: 0; right: 0; bottom: -1px; height: 2px; background: var(--cl-gradient-brand); opacity: .55; }}
.cl-sidebar {{ background: var(--cl-sidebar) !important; color: var(--cl-sidebar-fg); border-right: 1px solid var(--cl-sidebar-border); }}
.cl-nav-group {{ font-size: .68rem; font-weight: 600; letter-spacing: .09em; text-transform: uppercase; color: var(--cl-sidebar-fg-muted); padding: 18px 16px 6px; }}
.cl-nav-item {{
  width: 100%; display: flex; align-items: center; gap: 12px; padding: 9px 14px; margin: 1px 8px; border-radius: var(--cl-radius-sm);
  color: var(--cl-sidebar-fg); font-size: .875rem; font-weight: 500; text-align: left; transition: background-color .12s ease, color .12s ease;
}}
.cl-nav-item:hover {{ background: var(--cl-sidebar-hover); color: #fff; }}
.cl-nav-item.cl-active {{ background: var(--cl-sidebar-active); color: #fff; font-weight: 600; }}
.cl-nav-item .q-icon {{ font-size: 1.25rem; opacity: .9; }}
.cl-brand-mark {{ display: flex; align-items: center; gap: 10px; padding: 16px; }}

/* ---- surfaces -------------------------------------------------------------------------- */
.cl-card {{
  background: var(--cl-surface); border: 1px solid var(--cl-border); border-radius: var(--cl-radius-lg);
  box-shadow: var(--cl-shadow-soft); padding: 18px;
}}
.cl-card-flat {{ background: var(--cl-surface); border: 1px solid var(--cl-border); border-radius: var(--cl-radius-lg); padding: 18px; box-shadow: none; }}
.cl-card-hover {{ transition: transform .15s ease, box-shadow .15s ease; cursor: pointer; }}
.cl-card-hover:hover {{ transform: translateY(-2px); box-shadow: var(--cl-shadow-lift); }}
.cl-surface-alt {{ background: var(--cl-surface-alt); border-radius: var(--cl-radius-lg); }}
.cl-divider {{ border-color: var(--cl-border) !important; }}

/* ---- stat tiles ------------------------------------------------------------------------ */
.cl-stat {{ min-width: 176px; flex: 1 1 176px; }}
.cl-stat-icon {{ width: 38px; height: 38px; border-radius: var(--cl-radius-md); display: flex; align-items: center; justify-content: center; }}
@media (max-width: 640px) {{ .cl-stat {{ min-width: 100%; flex-basis: 100%; }} }}

/* ---- badges / chips --------------------------------------------------------------------- */
.cl-badge {{
  display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: var(--cl-radius-pill);
  font-size: .72rem; font-weight: 600; letter-spacing: .01em; line-height: 1.6; white-space: nowrap;
}}
.cl-badge .q-icon {{ font-size: 1rem; }}
"""

for _name in ("primary", "secondary", "success", "warning", "danger", "info", "ai", "emergency", "muted"):
    CSS += f".cl-badge-{_name} {{ background: var(--cl-{_name}-soft); color: var(--cl-{_name}); }}\n"
    CSS += f".cl-dot-{_name} {{ background: var(--cl-{_name}); }}\n"

CSS += """
.cl-badge-outline { background: transparent; border: 1px solid var(--cl-border-strong); color: var(--cl-fg-muted); }
.cl-dot { width: 8px; height: 8px; border-radius: 999px; display: inline-block; flex: none; }

/* ---- empty / loading / error states ------------------------------------------------------ */
.cl-state { display: flex; flex-direction: column; align-items: center; text-align: center; width: 100%; padding: 40px 20px; color: var(--cl-fg-muted); gap: 6px; }
.cl-state .q-icon { font-size: 2.25rem; color: var(--cl-fg-subtle); margin-bottom: 6px; }
.cl-state-title { color: var(--cl-fg); font-weight: 600; font-size: .95rem; }
.cl-state-body { font-size: .84rem; max-width: 420px; }

@keyframes cl-shimmer { 0% { background-position: -300px 0; } 100% { background-position: 300px 0; } }
.cl-skeleton {
  border-radius: var(--cl-radius-sm); background: linear-gradient(90deg, var(--cl-surface-alt) 25%, var(--cl-surface-hover) 37%, var(--cl-surface-alt) 63%);
  background-size: 600px 100%; animation: cl-shimmer 1.4s ease infinite;
}
@media (prefers-reduced-motion: reduce) { .cl-skeleton { animation: none; } }

/* ---- timeline ---------------------------------------------------------------------------- */
.cl-timeline { position: relative; padding-left: 28px; }
.cl-timeline::before { content: ""; position: absolute; left: 9px; top: 4px; bottom: 4px; width: 2px; background: var(--cl-border); }
.cl-timeline-step { position: relative; padding-bottom: 22px; }
.cl-timeline-step:last-child { padding-bottom: 0; }
.cl-timeline-dot { position: absolute; left: -28px; top: 2px; width: 20px; height: 20px; border-radius: 999px; display: flex; align-items: center; justify-content: center; background: var(--cl-surface); border: 2px solid var(--cl-border-strong); }
.cl-timeline-dot .q-icon { font-size: .9rem; }
.cl-timeline-dot.cl-done { border-color: var(--cl-success); background: var(--cl-success-soft); color: var(--cl-success); }
.cl-timeline-dot.cl-current { border-color: var(--cl-primary); background: var(--cl-primary-soft); color: var(--cl-primary); }
.cl-timeline-dot.cl-rejected { border-color: var(--cl-danger); background: var(--cl-danger-soft); color: var(--cl-danger); }

/* ---- stepper ------------------------------------------------------------------------------ */
.cl-steps { display: flex; align-items: center; gap: 6px; width: 100%; overflow-x: auto; padding-bottom: 4px; }
.cl-step { display: flex; align-items: center; gap: 8px; padding: 6px 12px 6px 6px; border-radius: var(--cl-radius-pill); flex: none; }
.cl-step-num { width: 24px; height: 24px; border-radius: 999px; display: flex; align-items: center; justify-content: center; font-size: .75rem; font-weight: 700; background: var(--cl-surface-alt); color: var(--cl-fg-muted); flex: none; }
.cl-step.cl-active .cl-step-num { background: var(--cl-primary); color: var(--cl-primary-fg); }
.cl-step.cl-done .cl-step-num { background: var(--cl-success); color: #fff; }
.cl-step-label { font-size: .82rem; color: var(--cl-fg-muted); white-space: nowrap; }
.cl-step.cl-active .cl-step-label { color: var(--cl-fg); font-weight: 600; }
.cl-step-sep { width: 20px; height: 1px; background: var(--cl-border-strong); flex: none; }

/* ---- chat (AI copilot) --------------------------------------------------------------------- */
.cl-chat-row { display: flex; width: 100%; margin-bottom: 12px; }
.cl-chat-row.cl-user { justify-content: flex-end; }
.cl-chat-bubble { max-width: 75%; padding: 10px 14px; border-radius: var(--cl-radius-lg); font-size: .89rem; line-height: 1.5; }
.cl-chat-row.cl-user .cl-chat-bubble { background: var(--cl-primary); color: var(--cl-primary-fg); border-bottom-right-radius: 4px; }
.cl-chat-row.cl-assistant .cl-chat-bubble { background: var(--cl-surface-alt); color: var(--cl-fg); border-bottom-left-radius: 4px; }
.cl-chat-avatar { width: 30px; height: 30px; border-radius: 999px; display: flex; align-items: center; justify-content: center; flex: none; background: var(--cl-ai-soft); color: var(--cl-ai); }

/* ---- upload dropzone ------------------------------------------------------------------------ */
.cl-dropzone { border: 1.5px dashed var(--cl-border-strong); border-radius: var(--cl-radius-lg); background: var(--cl-surface-alt); transition: border-color .12s ease, background-color .12s ease; }
.cl-dropzone:hover { border-color: var(--cl-primary); background: var(--cl-primary-soft); }

/* ---- misc ------------------------------------------------------------------------------------ */
.cl-kbd { font-family: var(--cl-font-mono); font-size: .72rem; background: var(--cl-surface-alt); border: 1px solid var(--cl-border-strong); border-radius: 4px; padding: 1px 6px; }
.cl-hairline { border-top: 1px solid var(--cl-border); }
.cl-clip-1 { display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; }
.cl-clip-2 { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

@media (prefers-reduced-motion: reduce) {
  * { animation-duration: 0.001ms !important; transition-duration: 0.001ms !important; }
}

/* ================================================================================================
   ADVANCED VISUAL LAYER: animated gradient-mesh backgrounds, glassmorphism, 3D hover depth, glow.
   Every effect below degrades gracefully (plain colour / no animation) if the browser lacks support,
   and every animation is killed by the prefers-reduced-motion rule above.
   ================================================================================================ */

/* ---- animated gradient-mesh background (auth pages, landing) --------------------------------- */
.cl-aurora {
  position: fixed; inset: 0; z-index: -1; overflow: hidden; background: var(--cl-bg);
}
.cl-aurora::after {
  content: ""; position: absolute; inset: -10%;
  background-image:
    linear-gradient(var(--cl-border) 1px, transparent 1px),
    linear-gradient(90deg, var(--cl-border) 1px, transparent 1px);
  background-size: 46px 46px;
  opacity: .5;
  -webkit-mask-image: radial-gradient(ellipse 60% 50% at 50% 40%, black 0%, transparent 72%);
  mask-image: radial-gradient(ellipse 60% 50% at 50% 40%, black 0%, transparent 72%);
}
.cl-blob {
  position: absolute; border-radius: 50%; filter: blur(70px); will-change: transform;
  animation: cl-blob-float 22s ease-in-out infinite;
}
body.body--dark .cl-blob { filter: blur(80px); opacity: .55; }
.cl-blob-1 { width: 46vw; height: 46vw; max-width: 560px; max-height: 560px; background: var(--cl-primary); opacity: .32; top: -14vw; left: -10vw; }
.cl-blob-2 { width: 40vw; height: 40vw; max-width: 500px; max-height: 500px; background: var(--cl-ai); opacity: .28; bottom: -16vw; right: -8vw; animation-delay: -7s; }
.cl-blob-3 { width: 32vw; height: 32vw; max-width: 420px; max-height: 420px; background: var(--cl-secondary); opacity: .24; top: 32%; right: 8%; animation-delay: -14s; }
@keyframes cl-blob-float {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(3vw, -2.5vw) scale(1.08); }
  66% { transform: translate(-2.5vw, 2vw) scale(.94); }
}

/* ---- glassmorphism surface --------------------------------------------------------------------- */
.cl-glass {
  background: var(--cl-glass-bg);
  -webkit-backdrop-filter: blur(22px) saturate(160%);
  backdrop-filter: blur(22px) saturate(160%);
  border: 1px solid var(--cl-glass-border);
  border-radius: var(--cl-radius-xl);
  box-shadow: var(--cl-shadow-lift), 0 0 60px -20px var(--cl-glow-primary);
}

/* ---- gradient text / chips / brand ------------------------------------------------------------- */
.cl-gradient-text {
  background: var(--cl-gradient-brand); -webkit-background-clip: text; background-clip: text; color: transparent;
}
.cl-brand-chip {
  background: var(--cl-gradient-brand); border-radius: var(--cl-radius-sm); display: flex; align-items: center;
  justify-content: center; box-shadow: 0 6px 18px -6px var(--cl-glow-primary); color: #fff;
}

/* ---- 3D hover depth: cards lift + tilt + glow instead of a flat translateY -------------------- */
.cl-card-hover {
  cursor: pointer; transform-style: preserve-3d;
  transition: transform .32s cubic-bezier(.2,.8,.2,1), box-shadow .32s ease, border-color .32s ease;
}
.cl-card-hover:hover {
  transform: perspective(1000px) rotateX(3deg) rotateY(-3deg) translateY(-6px) scale(1.015);
  box-shadow: var(--cl-shadow-lift), 0 0 40px -12px var(--cl-glow-primary);
  border-color: color-mix(in srgb, var(--cl-primary) 35%, var(--cl-border));
}
.cl-card-hover:active { transform: perspective(1000px) translateY(-1px) scale(1.005); }

/* stat tiles get a permanent gradient accent bar + gentle lift on hover, no click affordance needed */
.cl-stat { position: relative; overflow: hidden; transition: transform .25s ease, box-shadow .25s ease; }
.cl-stat::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--cl-gradient-brand); }
.cl-stat:hover { transform: translateY(-3px); box-shadow: var(--cl-shadow-lift); }

/* ---- glow buttons for primary calls-to-action -------------------------------------------------- */
.cl-btn-glow.q-btn {
  background: var(--cl-gradient-brand) !important; color: #fff !important;
  box-shadow: 0 10px 28px -10px var(--cl-glow-primary) !important;
  transition: transform .18s ease, box-shadow .18s ease !important;
}
.cl-btn-glow.q-btn:hover { transform: translateY(-2px); box-shadow: 0 16px 36px -10px var(--cl-glow-primary) !important; }
.cl-btn-glow.q-btn:active { transform: translateY(0); }

/* ---- sidebar: gradient active state with a glowing edge indicator ----------------------------- */
.cl-nav-item.cl-active {
  background: linear-gradient(120deg, var(--cl-sidebar-active), color-mix(in srgb, var(--cl-ai) 40%, var(--cl-sidebar-active)));
  color: #fff; font-weight: 600; position: relative;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.08);
}
.cl-nav-item.cl-active::before {
  content: ""; position: absolute; left: -8px; top: 18%; bottom: 18%; width: 3px; border-radius: 3px;
  background: var(--cl-ai); box-shadow: 0 0 12px 1px var(--cl-ai);
}

/* ---- segmented control: the citizen / government-official portal switcher --------------------- */
.cl-segment { display: flex; gap: 4px; padding: 5px; border-radius: var(--cl-radius-pill); background: var(--cl-surface-alt); border: 1px solid var(--cl-border); width: 100%; }
.cl-segment-item {
  flex: 1 1 0; display: flex; align-items: center; justify-content: center; gap: 8px; padding: 10px 14px;
  border-radius: var(--cl-radius-pill); font-size: .84rem; font-weight: 600; color: var(--cl-fg-muted);
  cursor: pointer; white-space: nowrap; transition: background .2s ease, color .2s ease, box-shadow .2s ease;
}
.cl-segment-item:hover { color: var(--cl-fg); }
.cl-segment-item.cl-on { color: #fff; box-shadow: 0 8px 22px -10px var(--cl-glow-primary); }
.cl-segment-item.cl-on.cl-citizen { background: var(--cl-gradient-brand); }
.cl-segment-item.cl-on.cl-official { background: linear-gradient(135deg, #8A5A16 0%, var(--cl-emergency) 100%); }
body.body--dark .cl-segment-item.cl-on.cl-official { background: linear-gradient(135deg, var(--cl-warning) 0%, var(--cl-emergency) 100%); }

/* ---- hero (landing) -------------------------------------------------------------------------- */
.cl-hero { text-align: center; padding: 64px 20px 28px; }
.cl-hero-title { font-size: clamp(2.5rem, 7vw, 4.25rem); font-weight: 800; letter-spacing: -.04em; line-height: 1.02; }
.cl-hero-sub { font-size: clamp(1rem, 2.2vw, 1.18rem); line-height: 1.6; color: var(--cl-fg-muted); max-width: 58ch; }
.cl-eyebrow {
  display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; border-radius: var(--cl-radius-pill);
  font-size: .76rem; font-weight: 600; letter-spacing: .02em;
  background: var(--cl-ai-soft); color: var(--cl-ai); border: 1px solid color-mix(in srgb, var(--cl-ai) 24%, transparent);
}
.cl-hero-strip { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px 28px; }
.cl-hero-stat-n { font-size: 1.6rem; font-weight: 800; letter-spacing: -.02em; color: var(--cl-fg); line-height: 1.1; }
.cl-hero-stat-l { font-size: .74rem; font-weight: 500; color: var(--cl-fg-subtle); text-transform: uppercase; letter-spacing: .07em; }

/* ---- feature tiles (landing + assistant) ------------------------------------------------------ */
.cl-tile { width: 210px; padding: 20px 18px; gap: 10px; display: flex; flex-direction: column; align-items: flex-start; }
@media (max-width: 520px) { .cl-tile { width: 100%; } }
.cl-tile-title { font-size: .95rem; font-weight: 700; color: var(--cl-fg); }
.cl-tile-body { font-size: .8rem; line-height: 1.5; color: var(--cl-fg-muted); }

/* ---- AI triage assistant ---------------------------------------------------------------------- */
.cl-ask {
  border-radius: var(--cl-radius-xl); padding: 6px 6px 6px 18px; display: flex; align-items: center; gap: 10px;
  background: var(--cl-surface); border: 1.5px solid var(--cl-border-strong); box-shadow: var(--cl-shadow-soft);
  transition: border-color .2s ease, box-shadow .2s ease;
}
.cl-ask:focus-within { border-color: var(--cl-ai); box-shadow: var(--cl-shadow-lift), 0 0 0 4px var(--cl-ai-soft); }
.cl-route-card { border-left: 4px solid var(--cl-ai); }
@keyframes cl-pulse-ring { 0% { box-shadow: 0 0 0 0 var(--cl-glow-ai); } 70% { box-shadow: 0 0 0 14px transparent; } 100% { box-shadow: 0 0 0 0 transparent; } }
.cl-mic-live { animation: cl-pulse-ring 1.6s ease-out infinite; }

@media (prefers-reduced-motion: reduce) {
  .cl-blob { animation: none; }
  .cl-mic-live { animation: none; }
}
"""

