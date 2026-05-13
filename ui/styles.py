"""Tokyo Night 風格的 QSS。"""


# 主要色票
COLORS = {
    "bg":           "#1a1b26",
    "panel":        "#1f2335",
    "panel_2":      "#24283b",
    "border":       "#2f334d",
    "border_focus": "#7aa2f7",
    "fg":           "#c0caf5",
    "fg_muted":     "#9aa5ce",
    "fg_dim":       "#565f89",
    "accent":       "#7aa2f7",  # 藍 — primary
    "accent_hover": "#89b4fa",
    "success":      "#9ece6a",  # 綠 — 數值
    "warning":      "#e0af68",  # 橘 — 注意
    "danger":       "#f7768e",  # 紅 — 危險
    "info":         "#7dcfff",  # 青 — 資訊
    "purple":       "#bb9af7",
}


def stylesheet() -> str:
    c = COLORS
    return f"""
    QWidget {{
        background-color: {c['bg']};
        color: {c['fg']};
        font-family: "Microsoft JhengHei UI", "PingFang TC", "Noto Sans CJK TC", sans-serif;
        font-size: 13px;
    }}

    QFrame#card {{
        background-color: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 12px;
    }}

    QFrame#card_inner {{
        background-color: {c['panel_2']};
        border: 1px solid {c['border']};
        border-radius: 10px;
    }}

    QLabel#title {{
        color: {c['fg']};
        font-size: 22px;
        font-weight: bold;
    }}

    QLabel#subtitle {{
        color: {c['fg_muted']};
        font-size: 12px;
    }}

    QLabel#section_label {{
        color: {c['fg_dim']};
        font-size: 11px;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}

    QLabel#metric_value {{
        color: {c['success']};
        font-family: "JetBrains Mono", "Consolas", monospace;
        font-size: 28px;
        font-weight: bold;
    }}

    QLabel#metric_value_small {{
        color: {c['fg']};
        font-family: "JetBrains Mono", "Consolas", monospace;
        font-size: 16px;
        font-weight: bold;
    }}

    QLabel#metric_label {{
        color: {c['fg_muted']};
        font-size: 11px;
    }}

    QLabel#rate_primary {{
        color: {c['accent']};
        font-family: "JetBrains Mono", "Consolas", monospace;
        font-size: 24px;
        font-weight: bold;
    }}

    QLabel#rate_secondary {{
        color: {c['fg']};
        font-family: "JetBrains Mono", "Consolas", monospace;
        font-size: 14px;
    }}

    QLabel#badge {{
        background-color: {c['panel_2']};
        color: {c['fg_muted']};
        border: 1px solid {c['border']};
        border-radius: 10px;
        padding: 4px 10px;
        font-size: 11px;
    }}

    QLabel#badge_live {{
        background-color: rgba(158, 206, 106, 25);
        color: {c['success']};
        border: 1px solid {c['success']};
        border-radius: 10px;
        padding: 4px 10px;
        font-size: 11px;
        font-weight: bold;
    }}

    QPushButton {{
        background-color: {c['panel_2']};
        color: {c['fg']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        padding: 8px 14px;
        font-size: 12px;
    }}

    QPushButton:hover {{
        background-color: {c['border']};
        border-color: {c['accent']};
    }}

    QPushButton:pressed {{
        background-color: {c['panel']};
    }}

    QPushButton:disabled {{
        color: {c['fg_dim']};
        background-color: {c['panel']};
    }}

    QPushButton#primary {{
        background-color: {c['accent']};
        color: {c['bg']};
        border: 1px solid {c['accent']};
        font-weight: bold;
    }}

    QPushButton#primary:hover {{
        background-color: {c['accent_hover']};
    }}

    QPushButton#danger {{
        background-color: transparent;
        color: {c['danger']};
        border: 1px solid {c['danger']};
    }}

    QPushButton#danger:hover {{
        background-color: rgba(247, 118, 142, 30);
    }}

    QPushButton#segment {{
        background-color: {c['panel_2']};
        color: {c['fg_muted']};
        border: 1px solid {c['border']};
        padding: 6px 10px;
        font-size: 11px;
    }}

    QPushButton#segment:checked {{
        background-color: {c['accent']};
        color: {c['bg']};
        border-color: {c['accent']};
        font-weight: bold;
    }}

    QComboBox {{
        background-color: {c['panel_2']};
        color: {c['fg']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        padding: 6px 10px;
        min-height: 24px;
    }}

    QComboBox:hover {{
        border-color: {c['accent']};
    }}

    QComboBox QAbstractItemView {{
        background-color: {c['panel_2']};
        color: {c['fg']};
        border: 1px solid {c['border']};
        selection-background-color: {c['accent']};
        selection-color: {c['bg']};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}

    QTabWidget::pane {{
        border: 1px solid {c['border']};
        border-radius: 8px;
        background-color: {c['panel']};
        top: -1px;
    }}

    QTabBar::tab {{
        background-color: transparent;
        color: {c['fg_muted']};
        padding: 8px 18px;
        border: 1px solid transparent;
        border-bottom: none;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        font-size: 12px;
    }}

    QTabBar::tab:selected {{
        background-color: {c['panel']};
        color: {c['fg']};
        border-color: {c['border']};
    }}

    QTabBar::tab:hover:!selected {{
        color: {c['fg']};
    }}

    QTextEdit, QPlainTextEdit {{
        background-color: {c['panel_2']};
        color: {c['fg']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        padding: 6px;
        font-family: "JetBrains Mono", "Consolas", monospace;
        font-size: 11px;
    }}

    QStatusBar {{
        background-color: {c['bg']};
        color: {c['fg_muted']};
        border-top: 1px solid {c['border']};
    }}

    QToolTip {{
        background-color: {c['panel_2']};
        color: {c['fg']};
        border: 1px solid {c['border']};
        padding: 4px;
    }}
    """
