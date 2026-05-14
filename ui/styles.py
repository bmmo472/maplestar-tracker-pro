"""炸彈黃 × 焦黑配色 — 呼應土豆地雷 icon。"""


# 主要色票 — 暗夜炸藥
COLORS = {
    "bg":           "#0c0a08",   # 焦黑背景
    "panel":        "#15110c",   # 卡片底（極深焦糖）
    "panel_2":      "#1f1812",   # 次層
    "border":       "#2e251c",   # 邊框（深焦糖）
    "border_focus": "#f0a040",
    "fg":           "#f5ead8",   # 暖白主文字
    "fg_muted":     "#8a7a5e",   # 中等淡褐
    "fg_dim":       "#4a3e2e",   # 標籤暗褐
    "accent":       "#f0a040",   # 炸彈火光橘 — primary
    "accent_hover": "#ffba60",
    "success":      "#d4e85a",   # 爆炸黃綠 — 數值
    "warning":      "#ff8030",   # 炸藥紅橘
    "danger":       "#e63950",   # 警告深紅
    "info":         "#dcc080",   # 沙土黃
    "purple":       "#c08050",   # 焦糖咖啡
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

    /* 緊湊資訊條（取代 Card） */
    QFrame#strip {{
        background-color: {c['panel']};
        border: none;
        border-top: 1px solid {c['border']};
        border-bottom: 1px solid {c['border']};
    }}

    QFrame#strip_hero {{
        background-color: {c['panel']};
        border: none;
    }}

    QFrame#strip_thin {{
        background-color: transparent;
        border-top: 1px solid {c['border']};
        border-bottom: none;
    }}

    /* Header */
    QLabel#title {{
        color: {c['accent']};
        font-size: 24px;
        font-weight: 900;
        letter-spacing: -0.5px;
    }}

    QLabel#version_line {{
        color: {c['fg_dim']};
        font-size: 11px;
        letter-spacing: 1px;
    }}

    /* 主要大數字 — 目前 EXP */
    QLabel#hero_value {{
        color: {c['success']};
        font-family: "JetBrains Mono", "Consolas", monospace;
        font-size: 56px;
        font-weight: 900;
        letter-spacing: -2px;
    }}

    QLabel#hero_label {{
        color: {c['fg_dim']};
        font-size: 10px;
        font-weight: bold;
        letter-spacing: 2.5px;
    }}

    /* 等級 + 百分比 */
    QLabel#level_value {{
        color: {c['accent']};
        font-family: "JetBrains Mono", "Consolas", monospace;
        font-size: 28px;
        font-weight: 800;
    }}

    QLabel#pct_value {{
        color: {c['fg']};
        font-family: "JetBrains Mono", "Consolas", monospace;
        font-size: 28px;
        font-weight: 800;
    }}

    /* 二級資訊 */
    QLabel#stat_value {{
        color: {c['fg']};
        font-family: "JetBrains Mono", "Consolas", monospace;
        font-size: 22px;
        font-weight: 700;
    }}

    QLabel#stat_value_warn {{
        color: {c['warning']};
        font-family: "JetBrains Mono", "Consolas", monospace;
        font-size: 22px;
        font-weight: 700;
    }}

    QLabel#stat_value_accent {{
        color: {c['accent']};
        font-family: "JetBrains Mono", "Consolas", monospace;
        font-size: 22px;
        font-weight: 700;
    }}

    QLabel#stat_label {{
        color: {c['fg_dim']};
        font-size: 10px;
        font-weight: bold;
        letter-spacing: 2px;
    }}

    QLabel#caption {{
        color: {c['fg_muted']};
        font-size: 11px;
    }}

    /* 進度條 */
    QProgressBar#hero_bar {{
        background-color: {c['panel_2']};
        border: 1px solid {c['border']};
        border-radius: 2px;
        max-height: 4px;
        min-height: 4px;
        text-align: center;
        color: transparent;
    }}

    QProgressBar#hero_bar::chunk {{
        background-color: {c['accent']};
        border-radius: 1px;
    }}

    /* 狀態徽章 */
    QLabel#badge {{
        background-color: transparent;
        color: {c['fg_dim']};
        border: 1px solid {c['border']};
        border-radius: 3px;
        padding: 3px 10px;
        font-size: 10px;
        letter-spacing: 1.5px;
        font-weight: bold;
    }}

    QLabel#badge_live {{
        background-color: {c['accent']};
        color: {c['bg']};
        border: 1px solid {c['accent']};
        border-radius: 3px;
        padding: 3px 10px;
        font-size: 10px;
        letter-spacing: 1.5px;
        font-weight: bold;
    }}

    /* 按鈕 — 方正、無圓角、邊框感 */
    QPushButton {{
        background-color: transparent;
        color: {c['fg_muted']};
        border: 1px solid {c['border']};
        border-radius: 2px;
        padding: 7px 14px;
        font-size: 12px;
        font-weight: bold;
        letter-spacing: 1px;
    }}

    QPushButton:hover {{
        color: {c['fg']};
        border-color: {c['accent']};
    }}

    QPushButton:pressed {{
        background-color: {c['panel_2']};
    }}

    QPushButton:disabled {{
        color: {c['fg_dim']};
        border-color: {c['border']};
    }}

    QPushButton#primary {{
        background-color: {c['accent']};
        color: {c['bg']};
        border: 1px solid {c['accent']};
    }}

    QPushButton#primary:hover {{
        background-color: {c['accent_hover']};
        border-color: {c['accent_hover']};
    }}

    QPushButton#danger {{
        background-color: transparent;
        color: {c['danger']};
        border: 1px solid {c['border']};
    }}

    QPushButton#danger:hover {{
        border-color: {c['danger']};
    }}

    QPushButton#segment {{
        background-color: transparent;
        color: {c['fg_muted']};
        border: 1px solid {c['border']};
        border-radius: 2px;
        padding: 5px 9px;
        font-size: 11px;
    }}

    QPushButton#segment:checked {{
        background-color: {c['accent']};
        color: {c['bg']};
        border-color: {c['accent']};
    }}

    /* 下拉選單 */
    QComboBox {{
        background-color: {c['panel_2']};
        color: {c['fg']};
        border: 1px solid {c['border']};
        border-radius: 2px;
        padding: 6px 10px;
        min-height: 22px;
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

    /* Tab */
    QTabWidget::pane {{
        border: 1px solid {c['border']};
        border-radius: 0;
        background-color: {c['panel']};
        top: -1px;
    }}

    QTabBar::tab {{
        background-color: transparent;
        color: {c['fg_dim']};
        padding: 8px 22px;
        border: 1px solid transparent;
        border-bottom: 2px solid transparent;
        font-size: 12px;
        font-weight: bold;
        letter-spacing: 1.5px;
    }}

    QTabBar::tab:selected {{
        color: {c['accent']};
        border-bottom: 2px solid {c['accent']};
    }}

    QTabBar::tab:hover:!selected {{
        color: {c['fg']};
    }}

    /* 狀態列 */
    QStatusBar {{
        background-color: {c['bg']};
        color: {c['fg_dim']};
        border-top: 1px solid {c['border']};
        font-size: 10px;
        letter-spacing: 1px;
    }}

    /* Tooltip */
    QToolTip {{
        background-color: {c['panel_2']};
        color: {c['fg']};
        border: 1px solid {c['border']};
        padding: 4px;
    }}
    """
