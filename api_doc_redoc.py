import json

import streamlit.components.v1 as components

from ui import tokens as t


def render_redoc(spec: dict, height: int = 850):
    """
    Render an OpenAPI spec as a ReDoc documentation page inside Streamlit,
    themed to match the neon Gen-Z UI.
    """
    spec_json = json.dumps(spec)

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    /* ── Reset ─────────────────────────────────────────────────────── */
    *, *::before, *::after {{ box-sizing: border-box; }}
    html, body {{
      margin: 0; padding: 0;
      background: {t.REDOC_BG_MAIN};
      color: {t.REDOC_TEXT_PRIMARY};
      font-family: {t.FONT_BODY};
    }}

    /* ── Outer wrapper ─────────────────────────────────────────────── */
    .redoc-wrap {{ background: {t.REDOC_BG_MAIN} !important; }}

    /* ── Sidebar ───────────────────────────────────────────────────── */
    .menu-content {{
      background: {t.REDOC_BG_SECONDARY} !important;
      border-right: 1px solid {t.REDOC_BORDER} !important;
    }}
    .scrollbar-container {{ background: {t.REDOC_BG_SECONDARY} !important; }}

    label[role="menuitem"] > span,
    .api-info {{ color: {t.REDOC_TEXT_PRIMARY} !important; }}

    li[data-item-id] > label {{ color: {t.REDOC_TEXT_MUTED} !important; }}
    li[data-item-id] > label:hover,
    li[data-item-id].active > label {{
      background: {t.REDOC_BG_ITEM} !important;
      color: {t.REDOC_ACCENT} !important;
    }}

    .search-box input {{
      background: {t.REDOC_BG_MAIN} !important;
      border: 1px solid {t.REDOC_BORDER} !important;
      color: {t.REDOC_TEXT_PRIMARY} !important;
    }}
    .search-box input:focus {{
      border-color: {t.NEON_CYAN} !important;
      box-shadow: 0 0 8px rgba(0, 245, 255, 0.25);
    }}
    .search-box input::placeholder {{ color: {t.REDOC_TEXT_MUTED} !important; }}
    .search-icon svg {{ fill: {t.REDOC_TEXT_MUTED} !important; }}

    [role="heading"] {{ color: {t.REDOC_TEXT_MUTED} !important; }}

    /* ── Main panel ─────────────────────────────────────────────────── */
    .api-content {{ background: {t.REDOC_BG_MAIN} !important; }}

    h1, h2, h3, h4, h5 {{
      color: {t.REDOC_TEXT_PRIMARY} !important;
      font-family: {t.FONT_HEADING};
    }}

    p, li, td, th, span {{
      color: {t.REDOC_TEXT_PRIMARY} !important;
    }}

    .api-info h1 {{ color: {t.REDOC_TEXT_PRIMARY} !important; }}
    .api-info p  {{ color: {t.REDOC_TEXT_MUTED}  !important; }}

    [data-section-id] h2 {{
      color: {t.REDOC_TEXT_PRIMARY} !important;
      border-bottom: 1px solid {t.REDOC_BORDER} !important;
    }}

    [data-section-id] {{
      background: {t.REDOC_BG_MAIN} !important;
      border-bottom: 1px solid {t.REDOC_BORDER} !important;
    }}
    .operation-type {{ color: {t.REDOC_TEXT_PRIMARY} !important; }}

    [data-section-id] summary h5 {{
      color: {t.REDOC_TEXT_PRIMARY} !important;
    }}

    [data-section-id] > div {{
      background: {t.REDOC_BG_MAIN} !important;
    }}

    .redoc-markdown p,
    .redoc-markdown li {{
      color: {t.REDOC_TEXT_MUTED} !important;
    }}

    /* ── HTTP method badges ─────────────────────────────────────────── */
    .http-verb {{
      font-weight: 700 !important;
      border-radius: 4px !important;
      padding: 2px 8px !important;
      box-shadow: 0 0 8px rgba(0, 245, 255, 0.2);
    }}
    .http-verb.get    {{ background: {t.BADGE_GET}  !important; color: #0A0A0F !important; }}
    .http-verb.post   {{ background: {t.BADGE_POST} !important; color: #0A0A0F !important; }}
    .http-verb.put    {{ background: {t.BADGE_PUT}  !important; color: #0A0A0F !important; }}
    .http-verb.patch  {{ background: {t.BADGE_PATCH}!important; color: #fff !important; }}
    .http-verb.delete {{ background: {t.BADGE_DELETE}  !important; color: #fff !important; }}

    /* ── Schema / type tables ───────────────────────────────────────── */
    table {{
      background: {t.REDOC_BG_SECONDARY} !important;
      border-collapse: collapse !important;
    }}
    th {{
      background: {t.REDOC_BG_ITEM}    !important;
      color: {t.REDOC_TEXT_MUTED}      !important;
      border-bottom: 1px solid {t.REDOC_BORDER} !important;
    }}
    td {{
      border-bottom: 1px solid {t.REDOC_BORDER} !important;
      color: {t.REDOC_TEXT_PRIMARY}    !important;
    }}
    tr:hover td {{ background: {t.REDOC_BG_ITEM} !important; }}

    .property-type {{ color: {t.REDOC_ACCENT} !important; }}

    .required-label {{ color: {t.NEON_PINK} !important; }}

    .enumValue {{
      background: {t.REDOC_BG_ITEM}    !important;
      color: {t.REDOC_TEXT_PRIMARY}    !important;
      border: 1px solid {t.REDOC_BORDER} !important;
      border-radius: 3px !important;
    }}

    /* ── Inline code / code blocks ──────────────────────────────────── */
    code {{
      background: {t.REDOC_BG_CODE}  !important;
      color: {t.NEON_LIME}           !important;
      border-radius: 3px       !important;
      padding: 1px 5px         !important;
      font-family: {t.FONT_MONO};
    }}
    pre, .hljs {{
      background: {t.REDOC_BG_CODE}  !important;
      color: {t.REDOC_TEXT_PRIMARY}   !important;
      border-radius: 6px       !important;
    }}

    [class*="right-panel"],
    [class*="rightPanel"] {{
      background: {t.REDOC_BG_CODE} !important;
    }}
    [class*="right-panel"] h3,
    [class*="right-panel"] h5 {{
      color: {t.REDOC_TEXT_MUTED}   !important;
    }}

    [class*="response-tab"],
    ul[role="tablist"] li {{
      color: {t.REDOC_TEXT_MUTED}      !important;
      border-bottom: 2px solid transparent !important;
    }}
    [class*="response-tab"][aria-selected="true"],
    ul[role="tablist"] li[aria-selected="true"] {{
      color: {t.REDOC_ACCENT}          !important;
      border-bottom: 2px solid {t.REDOC_ACCENT} !important;
    }}

    [class*="arrow"],
    [class*="chevron"] svg {{ fill: {t.REDOC_TEXT_MUTED} !important; }}

    a {{ color: {t.REDOC_ACCENT} !important; }}
    a:hover {{ color: {t.NEON_MAGENTA} !important; text-shadow: 0 0 8px rgba(255, 0, 255, 0.4); }}

    [download], button[class*="download"] {{
      background: {t.REDOC_BG_SECONDARY}  !important;
      color: {t.REDOC_TEXT_PRIMARY}        !important;
      border: 1px solid {t.REDOC_BORDER}  !important;
      border-radius: 6px            !important;
    }}
    [download]:hover {{
      background: {t.REDOC_BG_ITEM}       !important;
      border-color: {t.NEON_CYAN} !important;
    }}

    ::-webkit-scrollbar       {{ width: 6px; height: 6px; }}
    ::-webkit-scrollbar-track {{ background: {t.REDOC_BG_SECONDARY}; }}
    ::-webkit-scrollbar-thumb {{ background: {t.REDOC_BORDER}; border-radius: 3px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: {t.REDOC_TEXT_MUTED}; }}
  </style>
</head>
<body>
  <div id="redoc-container"></div>
  <script src="https://cdn.jsdelivr.net/npm/redoc@{t.REDOC_VERSION}/bundles/redoc.standalone.js"></script>
  <script>
    Redoc.init(
      {spec_json},
      {{
        scrollYOffset:      0,
        hideDownloadButton: false,
        expandResponses:    "200,201",
        pathInMiddlePanel:  true,
        nativeScrollbars:   false,
        theme: {{
          colors: {{
            primary: {{ main: "{t.REDOC_ACCENT}" }},
            text: {{
              primary:   "{t.REDOC_TEXT_PRIMARY}",
              secondary: "{t.REDOC_TEXT_MUTED}"
            }},
            border: {{ light: "{t.REDOC_BORDER}", dark: "{t.REDOC_BORDER}" }},
            responses: {{
              success:  {{ color: "{t.NEON_LIME}", backgroundColor: "#0A2A0A" }},
              error:    {{ color: "{t.NEON_PINK}", backgroundColor: "#2A0014" }},
              redirect: {{ color: "{t.NEON_YELLOW}", backgroundColor: "#2A2000" }},
              info:     {{ color: "{t.REDOC_ACCENT}", backgroundColor: "#14101F" }}
            }},
            http: {{
              get:    "{t.BADGE_GET}",
              post:   "{t.BADGE_POST}",
              put:    "{t.BADGE_PUT}",
              patch:  "{t.BADGE_PATCH}",
              delete: "{t.BADGE_DELETE}"
            }}
          }},
          typography: {{
            fontSize:    "14px",
            lineHeight:  "1.6",
            fontFamily:  {json.dumps(t.FONT_BODY)},
            headings: {{
              fontFamily: {json.dumps(t.FONT_HEADING)},
              fontWeight: "600"
            }},
            code: {{
              fontSize:   "13px",
              fontFamily: {json.dumps(t.FONT_MONO)},
              color:      "{t.NEON_LIME}",
              backgroundColor: "{t.REDOC_BG_CODE}"
            }}
          }},
          sidebar: {{
            width:           "260px",
            backgroundColor: "{t.REDOC_BG_SECONDARY}",
            textColor:       "{t.REDOC_TEXT_MUTED}"
          }},
          rightPanel: {{
            backgroundColor: "{t.REDOC_BG_CODE}",
            textColor:       "{t.REDOC_TEXT_PRIMARY}",
            width:           "40%"
          }},
          codeBlock: {{
            backgroundColor: "{t.REDOC_BG_CODE}"
          }}
        }}
      }},
      document.getElementById("redoc-container")
    );
  </script>
</body>
</html>"""

    components.html(html, height=height, scrolling=True)
