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

# Typography follows the mobile app's design system (mobile/legacy-prototype/src/constants/theme.js):
# Fraunces, an editorial serif with real character, carries headlines and hero moments - the weight
# you'd expect on a statute or a formal notice - and Manrope carries all UI/body text. The previous
# Inter-on-slate combination was the generic SaaS default and gave the product no identity of its own.
FONT_STACK = "'Manrope', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
FONT_DISPLAY = "'Fraunces', 'Iowan Old Style', Georgia, 'Times New Roman', serif"
FONT_MONO = "'JetBrains Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace"

# ---------------------------------------------------------------------------------------------
# Colour tokens
# ---------------------------------------------------------------------------------------------

# "Rajmudra" palette, shared with the mobile app's design system: the deep indigo of an official
# seal and judicial robes, the warm sandstone/terracotta of government buildings, and turmeric ochre
# from official ceremony - rather than the blue-on-slate kit every admin dashboard ships with.
# Backgrounds and text are warm (ledger paper), never clinical cool grey.
LIGHT: dict[str, str] = {
    "bg": "#FAF7EF",
    "surface": "#FFFFFF",
    "surface-alt": "#F3EEE1",
    "surface-hover": "#EAE3D2",
    "fg": "#201E13",
    "fg-muted": "#4A4632",
    "fg-subtle": "#79735A",
    "border": "#E7DFC9",
    "border-strong": "#D6CCAE",
    "primary": "#2A3785",
    "primary-strong": "#1D2760",
    "primary-soft": "#E7E9F5",
    "primary-fg": "#FFFFFF",
    "secondary": "#1F7A6D",
    "secondary-soft": "#E2F0ED",
    "success": "#1F7A4C",
    "success-soft": "#E3F1E8",
    "warning": "#9C7025",
    "warning-soft": "#F7EEDC",
    "danger": "#B23A3A",
    "danger-soft": "#F9E7E5",
    "info": "#28728A",
    "info-soft": "#E3EFF3",
    "ai": "#654A96",
    "ai-soft": "#EDE8F5",
    "emergency": "#9C3A50",
    "emergency-soft": "#F8E6E9",
    "muted": "#79735A",
    "muted-soft": "#F0EADB",
    "sidebar": "#1D2760",
    "sidebar-fg": "#D8D3C2",
    "sidebar-fg-muted": "#9C9683",
    "sidebar-hover": "#28336F",
    "sidebar-active": "#3547A8",
    "sidebar-border": "rgba(242,239,230,0.10)",
    "glow-primary": "rgba(42,55,133,.30)",
    "glow-ai": "rgba(101,74,150,.30)",
    "glass-bg": "rgba(255,255,255,.70)",
    "glass-border": "rgba(255,255,255,.60)",
}

# Dark mode is indigo-charcoal, not neutral slate, and text stays warm off-white (ledger paper).
DARK: dict[str, str] = {
    "bg": "#0B0E1A",
    "surface": "#12162A",
    "surface-alt": "#1B2140",
    "surface-hover": "#262E52",
    "fg": "#F2EFE6",
    "fg-muted": "#C7C2AF",
    "fg-subtle": "#8D8874",
    "border": "rgba(242,239,230,0.10)",
    "border-strong": "rgba(242,239,230,0.20)",
    "primary": "#5568D6",
    "primary-strong": "#7C8CE8",
    "primary-soft": "#1E2542",
    "primary-fg": "#0B0E1A",
    "secondary": "#2E9E8F",
    "secondary-soft": "#10322F",
    "success": "#2E9E63",
    "success-soft": "#11301F",
    "warning": "#BE8A2E",
    "warning-soft": "#33260D",
    "danger": "#C24545",
    "danger-soft": "#34191A",
    "info": "#3B8FA8",
    "info-soft": "#122C34",
    "ai": "#9B7FD4",
    "ai-soft": "#221A36",
    "emergency": "#B0435C",
    "emergency-soft": "#331620",
    "muted": "#8D8874",
    "muted-soft": "#1B2140",
    "sidebar": "#080B14",
    "sidebar-fg": "#D3CEBD",
    "sidebar-fg-muted": "#8D8874",
    "sidebar-hover": "#141A33",
    "sidebar-active": "#2A3785",
    "sidebar-border": "rgba(242,239,230,0.07)",
    "glow-primary": "rgba(85,104,214,.45)",
    "glow-ai": "rgba(155,127,212,.50)",
    "glass-bg": "rgba(18,22,42,.66)",
    "glass-border": "rgba(242,239,230,.10)",
}

RADIUS = {"xs": "6px", "sm": "8px", "md": "12px", "lg": "16px", "xl": "22px", "pill": "999px"}

# Shadows are tinted with the warm ink colour, not cold blue-grey, so cards sit on paper.
SHADOW = {
    "light-soft": "0 1px 2px rgba(32,30,19,.05), 0 6px 16px -8px rgba(32,30,19,.14)",
    "light-lift": "0 2px 8px rgba(32,30,19,.09), 0 20px 36px -18px rgba(32,30,19,.24)",
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


FONT_IMPORT = "@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');"

CSS = f"""
{FONT_IMPORT}
:root {{
{_vars(LIGHT)}
  --cl-radius-xs: {RADIUS["xs"]}; --cl-radius-sm: {RADIUS["sm"]}; --cl-radius-md: {RADIUS["md"]};
  --cl-radius-lg: {RADIUS["lg"]}; --cl-radius-xl: {RADIUS["xl"]}; --cl-radius-pill: {RADIUS["pill"]};
  --cl-shadow-soft: {SHADOW["light-soft"]};
  --cl-shadow-lift: {SHADOW["light-lift"]};
  --cl-font: {FONT_STACK};
  --cl-font-display: {FONT_DISPLAY};
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
  /* On near-black the light-mode brand ramp reads as muddy indigo, so the dark ramp starts from
     brighter stops - the hero wordmark is gradient-clipped text and needs the extra luminance. */
  --cl-gradient-brand: linear-gradient(135deg, #9FB0FF 0%, #7C8CE8 45%, #C2A6F5 100%) !important;
{_quasar_colors("dark")}
}}

/* ---- base ------------------------------------------------------------------------------- */
* {{ box-sizing: border-box; }}
/* ``html`` carries the base colour and ``body`` stays transparent on purpose: a negative-z-index
   element paints *behind* its parent's own background, so an opaque body would hide ``.cl-aurora``
   (z-index -1) entirely - which is what kept the gradient mesh and blobs invisible. With the colour
   on ``html`` it propagates to the canvas and the aurora paints above it, still below all content. */
html {{ background: {LIGHT["bg"]}; }}
/* Quasar toggles ``body--dark`` on <body>, which ``html`` can never match with a descendant
   selector, so the canvas colour is switched explicitly - via :has() for an in-app theme toggle and
   via the media query for a dark OS on first paint. Without this the canvas stays cream while the
   content renders dark, and the aurora shows through as a light background under dark cards. */
html:has(body.body--dark) {{ background: {DARK["bg"]}; }}
@media (prefers-color-scheme: dark) {{ html {{ background: {DARK["bg"]}; }} }}
@media (prefers-color-scheme: dark) {{ html:has(body:not(.body--dark)) {{ background: {LIGHT["bg"]}; }} }}
body {{
  background: transparent !important;
  color: var(--cl-fg) !important;
  font-family: var(--cl-font);
  -webkit-font-smoothing: antialiased;
  transition: background-color .16s ease, color .16s ease;
}}
/* These must stay transparent: ``.cl-aurora`` is a fixed layer at z-index -1, so any opaque
   background on the page wrapper paints straight over the gradient mesh and blobs and the whole
   decorative background silently disappears. ``body`` keeps the solid colour as the base layer. */
.q-page, .q-page-container, .q-layout {{ background: transparent; }}
/* Default browser link styling (pure blue + permanent underline) is one of the strongest "unstyled
   page" tells. Quasar's stylesheet is injected after this one, so plain ``a`` rules lose the
   cascade - hence the raised specificity and !important. ``.q-btn``/``.q-item``/``.cl-nav-item`` (sidebar) are excluded because
   Quasar renders some buttons and nav rows as anchors and they must keep their own styling. */
body a:not(.q-btn):not(.q-item):not(.q-tab):not(.cl-nav-item) {{
  color: var(--cl-primary) !important; text-decoration: none !important; transition: color .15s ease;
}}
body a:not(.q-btn):not(.q-item):not(.q-tab):not(.cl-nav-item):hover, body a:not(.q-btn):not(.q-item):not(.q-tab):not(.cl-nav-item):focus-visible {{
  text-decoration: underline !important; text-underline-offset: 3px;
}}
body.body--dark a:not(.q-btn):not(.q-item):not(.q-tab):not(.cl-nav-item) {{ color: var(--cl-primary-strong) !important; }}
/* Editorial serif for titles and headline numbers only; all UI/body text stays in Manrope, which
   is far more legible at small sizes. ``cl-title`` is applied by page_header/section_title. */
.cl-title, .cl-hero-title, .cl-hero-stat-n, .cl-stat-value {{ font-family: var(--cl-font-display); font-weight: 600; letter-spacing: -.015em; }}
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
.cl-skip-link:focus-visible {{ top: 12px; }}  /* keyboard focus only: a dialog handing focus back must not flash it */

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
  color: var(--cl-sidebar-fg); font-size: .875rem; font-weight: 500; text-align: left; text-decoration: none; transition: background-color .12s ease, color .12s ease;
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
.cl-dropzone { border: 1.5px dashed var(--cl-border-strong); border-radius: var(--cl-radius-lg); background: var(--cl-surface-alt); transition: border-color .12s ease, background-color .12s ease, transform .2s ease; overflow: hidden; }
.cl-dropzone:hover { border-color: var(--cl-primary); background: var(--cl-primary-soft); transform: translateY(-1px); }
/* Quasar's uploader always renders a "0 B / 0.00%" progress subtitle even when idle - real upload
   progress is still shown per-file (.q-uploader__file-status), so hiding the header's is cosmetic
   only, never hides real state. */
.cl-dropzone .q-uploader__subtitle { display: none; }
.cl-dropzone .q-uploader__header { background: transparent; }
.cl-dropzone .q-uploader__title { font-weight: 600; color: var(--cl-fg); }

/* A secondary "attach instead" affordance next to a primary action button (e.g. Legal Analyzer's
   Analyze button) - same uploader, but sized to sit beside a button instead of dominating the row. */
.cl-upload-compact { width: 15rem; max-width: 100%; }
.cl-upload-compact .q-uploader__header { min-height: 40px; padding: 6px 12px; background: transparent; border: 1.5px dashed var(--cl-border-strong); border-radius: var(--cl-radius-md); }
.cl-upload-compact .q-uploader__title { font-size: 13px; font-weight: 500; color: var(--cl-fg-muted); }
.cl-upload-compact .q-uploader__subtitle, .cl-upload-compact .q-uploader__list { display: none; }

/* ---- markdown-rendered AI text (interpretation, deep-dive law explanations) - tight spacing so it
   reads like normal prose inside a card, not a full markdown document with browser-default margins */
.cl-markdown p { margin: 0 0 8px 0; }
.cl-markdown p:last-child { margin-bottom: 0; }
.cl-markdown ul, .cl-markdown ol { margin: 4px 0 8px 0; padding-left: 1.3em; }
.cl-markdown li { margin-bottom: 2px; }
.cl-markdown strong { color: var(--cl-fg); font-weight: 700; }

/* ---- a hyperlink styled as a button, for an external link (never a real ui.button - Quasar can't
   navigate an <a> the way a real link does across browsers/popup-blockers the way ui.link can) --- */
.cl-link-btn { display: inline-flex; align-items: center; gap: 8px; padding: 9px 18px; border-radius: var(--cl-radius-md);
  background: var(--cl-primary); color: #fff !important; font-weight: 600; font-size: 13px; text-decoration: none !important;
  transition: transform .18s ease, box-shadow .18s ease; box-shadow: 0 8px 20px -10px var(--cl-glow-primary); }
.cl-link-btn:hover { transform: translateY(-2px); box-shadow: 0 12px 28px -10px var(--cl-glow-primary); }

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
  position: fixed; inset: 0; z-index: -1; overflow: hidden; background: transparent;
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
.cl-hero { text-align: center; padding: 40px 20px 20px; }
.cl-hero-title { font-size: clamp(2.5rem, 7vw, 4.25rem); font-weight: 700; letter-spacing: -.03em; line-height: 1.04; }
.cl-hero-sub { font-size: clamp(1rem, 2.2vw, 1.18rem); line-height: 1.6; color: var(--cl-fg-muted); max-width: 58ch; }
.cl-eyebrow {
  display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; border-radius: var(--cl-radius-pill);
  font-size: .76rem; font-weight: 600; letter-spacing: .02em;
  background: var(--cl-ai-soft); color: var(--cl-ai); border: 1px solid color-mix(in srgb, var(--cl-ai) 24%, transparent);
}
.cl-hero-strip { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px 28px; }
.cl-hero-stat-n { font-size: 1.75rem; font-weight: 700; letter-spacing: -.02em; color: var(--cl-fg); line-height: 1.1; }
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

/* ---- Civic Saathi ------------------------------------------------------------------------------- */
.cl-saathi { width: 100%; max-width: 960px; }
.cl-saathi-hero { position: relative; overflow: hidden; border-radius: var(--cl-radius-xl); padding: 22px 24px;
  background: linear-gradient(135deg, color-mix(in srgb, var(--cl-ai) 16%, var(--cl-surface)) 0%, var(--cl-surface) 55%, color-mix(in srgb, var(--cl-primary) 12%, var(--cl-surface)) 100%);
  border: 1px solid var(--cl-border); }
.cl-orb { width: 58px; height: 58px; border-radius: 999px; flex: none; display: flex; align-items: center; justify-content: center; color: #fff;
  background: conic-gradient(from 0deg, var(--cl-ai), var(--cl-primary), var(--cl-secondary), var(--cl-ai)); animation: cl-orb-spin 6s linear infinite;
  box-shadow: 0 0 0 4px var(--cl-ai-soft), 0 10px 30px -8px var(--cl-glow-ai); }
.cl-orb > i { animation: cl-orb-spin 6s linear infinite reverse; }
@keyframes cl-orb-spin { to { transform: rotate(360deg); } }
.cl-cap { display: inline-flex; align-items: center; gap: 6px; font-size: .74rem; font-weight: 600; padding: 5px 11px; border-radius: 999px;
  background: var(--cl-surface); border: 1px solid var(--cl-border); color: var(--cl-fg-muted); }
.cl-cap i { font-size: 15px; color: var(--cl-ai); }
.cl-saathi-panel { border-radius: var(--cl-radius-xl); border: 1px solid var(--cl-border); background: var(--cl-surface); overflow: hidden; box-shadow: var(--cl-shadow-soft); }
.cl-saathi-log { min-height: 300px; max-height: 58vh; overflow-y: auto; scroll-behavior: smooth; }
.cl-suggest-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
@media (max-width: 640px) { .cl-suggest-grid { grid-template-columns: 1fr; } }
.cl-suggest { cursor: pointer; text-align: left; border-radius: var(--cl-radius-lg); padding: 14px 16px; border: 1px solid var(--cl-border);
  background: var(--cl-surface-alt); transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease; }
.cl-suggest:hover, .cl-suggest:focus-visible { transform: translateY(-2px); border-color: var(--cl-ai); box-shadow: 0 10px 24px -14px var(--cl-glow-ai); outline: none; }
.cl-suggest i { color: var(--cl-ai); }
.cl-chat-md { font-size: .9rem; line-height: 1.6; color: inherit; }
.cl-chat-md p { margin: 0 0 .5em; } .cl-chat-md p:last-child { margin-bottom: 0; }
.cl-chat-md table { border-collapse: collapse; margin: .4em 0; font-size: .82rem; width: 100%; }
.cl-chat-md th, .cl-chat-md td { border: 1px solid var(--cl-border); padding: 5px 8px; text-align: left; }
.cl-chat-md th { background: var(--cl-surface); }
.cl-chat-md ol, .cl-chat-md ul { margin: .3em 0 .3em 1.2em; padding: 0; }
.cl-src { display: inline-flex; align-items: center; gap: 5px; font-size: .7rem; font-weight: 700; letter-spacing: .02em; padding: 3px 9px; border-radius: 999px; }
.cl-src i { font-size: 13px; }
.cl-src.records { background: var(--cl-success-soft); color: var(--cl-success); }
.cl-src.docs { background: var(--cl-info-soft); color: var(--cl-info); }
.cl-src.guidance { background: var(--cl-ai-soft); color: var(--cl-ai); }
.cl-src.unverified { background: var(--cl-warning-soft); color: var(--cl-warning); }
.cl-typing { display: inline-flex; gap: 5px; padding: 12px 16px; border-radius: var(--cl-radius-lg); background: var(--cl-surface-alt); }
.cl-typing span { width: 7px; height: 7px; border-radius: 999px; background: var(--cl-ai); animation: cl-bounce 1.2s infinite ease-in-out; }
.cl-typing span:nth-child(2) { animation-delay: .15s; } .cl-typing span:nth-child(3) { animation-delay: .3s; }
@keyframes cl-bounce { 0%, 80%, 100% { transform: translateY(0); opacity: .4; } 40% { transform: translateY(-6px); opacity: 1; } }
.cl-wave { display: inline-flex; align-items: center; gap: 3px; height: 18px; }
.cl-wave span { width: 3px; border-radius: 3px; background: var(--cl-danger); animation: cl-wave 1s ease-in-out infinite; }
.cl-wave span:nth-child(2) { animation-delay: .1s; } .cl-wave span:nth-child(3) { animation-delay: .2s; } .cl-wave span:nth-child(4) { animation-delay: .3s; } .cl-wave span:nth-child(5) { animation-delay: .4s; }
@keyframes cl-wave { 0%, 100% { height: 4px; } 50% { height: 18px; } }
.cl-saathi-bar { border-top: 1px solid var(--cl-border); background: var(--cl-surface-alt); }
.cl-mic-btn.cl-mic-live { background: var(--cl-danger) !important; color: #fff !important; }
.cl-saathi-intro { min-width: 220px; }
.cl-saathi-inputrow { flex-wrap: nowrap; }
.cl-saathi-box { min-width: 0; }
@media (max-width: 640px) {
  .cl-saathi-hero { padding: 16px; gap: 12px; }
  .cl-orb { width: 46px; height: 46px; }
  .cl-saathi-inputrow { flex-wrap: wrap; }
  .cl-spoken { order: -1; flex: 1 1 100%; width: 100% !important; }
  .cl-saathi-log { max-height: 62vh; }
}

@media (prefers-reduced-motion: reduce) {
  .cl-blob { animation: none; }
  .cl-mic-live { animation: none; }
  .cl-orb, .cl-orb > i, .cl-typing span, .cl-wave span { animation: none; }
}
"""

