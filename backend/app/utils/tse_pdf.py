"""
Dossie PDF do candidato — v2 editorial.

Layout:
  PAG 1 — CAPA: charcoal full-bleed, foto, nome enorme, partido, status,
                mini-mapa do Brasil com municipios em dourado + QR code
                pra versao online.
  PAG 2 — SUMARIO: indice das secoes com pagina aproximada.
  PAG 3 — VISAO GERAL: stats grandes + perfil patrimonial + redes +
                pizza de votos por UF (top 5 + outros).
  PAG 4+ — VOTOS POR MUNICIPIO: top 50 com barras horizontais.
  PAG N — VOTOS POR ZONA: top 30 com barras.
  RODAPE — em todas as paginas internas: faixa charcoal com paginacao
                e branding.
"""
from __future__ import annotations

from collections import Counter
from io import BytesIO
from typing import Iterable

import qrcode
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Flowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# -------------------------------------------------- paleta refinada
# Menos amarelao agressivo; champanhe + charcoal predominam.
GOLD = colors.HexColor("#C9A24B")
GOLD_DARK = colors.HexColor("#8C6E2A")
CHAMPAGNE = colors.HexColor("#E8D5A0")
CHAMPAGNE_PALE = colors.HexColor("#F2E6C8")
CHARCOAL = colors.HexColor("#1B1714")
CHARCOAL_2 = colors.HexColor("#2B2622")
CHARCOAL_3 = colors.HexColor("#3A332D")
CREAM = colors.HexColor("#FAF6EC")
CREAM_DARK = colors.HexColor("#EFE5CC")
WHITE = colors.HexColor("#FFFFFF")
MUTED = colors.HexColor("#6E6358")
MUTED_LIGHT = colors.HexColor("#A39785")
BORDER = colors.HexColor("#D8CFBE")

GREEN = colors.HexColor("#1F8A4C")
AMBER = colors.HexColor("#B07B17")
RED = colors.HexColor("#B43E2B")

# Paleta multi-cor pro pie chart (UFs).
PIE_PALETTE = [
    colors.HexColor("#C9A24B"),  # gold
    colors.HexColor("#8C6E2A"),  # gold dark
    colors.HexColor("#1F5A7A"),  # azul charcoal
    colors.HexColor("#7B1F32"),  # bordo
    colors.HexColor("#3E6B47"),  # verde escuro
    colors.HexColor("#6E6358"),  # muted (outros)
]


def _fmt_int(n: int | None) -> str:
    if n is None:
        return "—"
    return f"{n:,}".replace(",", ".")


def _fmt_brl(v: float | None) -> str:
    if v is None:
        return "—"
    s = f"{v:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    s: dict[str, ParagraphStyle] = {}
    # === CAPA ===
    s["cover_kicker"] = ParagraphStyle(
        "cover_kicker", parent=base["BodyText"], fontName="Helvetica-Bold",
        fontSize=8, leading=11, textColor=CHAMPAGNE, alignment=1,
        spaceAfter=4,
    )
    s["cover_name"] = ParagraphStyle(
        "cover_name", parent=base["Heading1"], fontName="Helvetica-Bold",
        fontSize=32, leading=36, textColor=WHITE, alignment=1,
        spaceAfter=2,
    )
    s["cover_legal"] = ParagraphStyle(
        "cover_legal", parent=base["BodyText"], fontName="Helvetica-Oblique",
        fontSize=10, leading=13, textColor=CHAMPAGNE_PALE, alignment=1,
    )
    s["cover_meta"] = ParagraphStyle(
        "cover_meta", parent=base["BodyText"], fontName="Helvetica",
        fontSize=10, leading=13, textColor=CREAM, alignment=1, spaceAfter=6,
    )
    s["cover_brand"] = ParagraphStyle(
        "cover_brand", parent=base["BodyText"], fontName="Helvetica-Bold",
        fontSize=9, leading=12, textColor=CHAMPAGNE, alignment=1,
    )
    s["cover_brand_sub"] = ParagraphStyle(
        "cover_brand_sub", parent=base["BodyText"], fontName="Helvetica",
        fontSize=6.5, leading=9, textColor=MUTED_LIGHT, alignment=1,
    )
    s["badge_cover"] = ParagraphStyle(
        "badge_cover", parent=base["BodyText"], fontName="Helvetica-Bold",
        fontSize=11, leading=13, textColor=WHITE, alignment=1,
    )
    # === SUMARIO ===
    s["toc_title"] = ParagraphStyle(
        "toc_title", parent=base["Heading1"], fontName="Helvetica-Bold",
        fontSize=11, leading=14, textColor=GOLD_DARK, alignment=0,
        spaceAfter=4,
    )
    s["toc_h2"] = ParagraphStyle(
        "toc_h2", parent=base["Heading2"], fontName="Helvetica-Bold",
        fontSize=24, leading=28, textColor=CHARCOAL, spaceAfter=18,
    )
    s["toc_item"] = ParagraphStyle(
        "toc_item", parent=base["BodyText"], fontName="Helvetica",
        fontSize=12, leading=18, textColor=CHARCOAL,
    )
    s["toc_page"] = ParagraphStyle(
        "toc_page", parent=base["BodyText"], fontName="Helvetica-Bold",
        fontSize=12, leading=18, textColor=GOLD_DARK, alignment=2,
    )
    # === INTERNAS ===
    s["section"] = ParagraphStyle(
        "section", parent=base["Heading2"], fontName="Helvetica-Bold",
        fontSize=9, leading=12, textColor=GOLD_DARK, spaceBefore=4,
        spaceAfter=8,
    )
    s["h2"] = ParagraphStyle(
        "h2", parent=base["Heading2"], fontName="Helvetica-Bold",
        fontSize=18, leading=22, textColor=CHARCOAL, spaceAfter=2,
    )
    s["sub"] = ParagraphStyle(
        "sub", parent=base["BodyText"], fontName="Helvetica",
        fontSize=10, leading=13, textColor=MUTED, spaceAfter=10,
    )
    s["body"] = ParagraphStyle(
        "body", parent=base["BodyText"], fontName="Helvetica",
        fontSize=10, leading=14, textColor=CHARCOAL,
    )
    s["small"] = ParagraphStyle(
        "small", parent=base["BodyText"], fontName="Helvetica",
        fontSize=8, leading=11, textColor=MUTED,
    )
    s["stat_label"] = ParagraphStyle(
        "stat_label", parent=base["BodyText"], fontName="Helvetica-Bold",
        fontSize=8, leading=10, textColor=GOLD_DARK, alignment=1,
    )
    s["stat_value"] = ParagraphStyle(
        "stat_value", parent=base["BodyText"], fontName="Helvetica-Bold",
        fontSize=22, leading=26, textColor=CHARCOAL, alignment=1,
    )
    s["stat_value_small"] = ParagraphStyle(
        "stat_value_small", parent=base["BodyText"], fontName="Helvetica-Bold",
        fontSize=14, leading=17, textColor=CHARCOAL, alignment=1,
    )
    s["table_th"] = ParagraphStyle(
        "table_th", parent=base["BodyText"], fontName="Helvetica-Bold",
        fontSize=7.5, leading=10, textColor=CHAMPAGNE,
    )
    s["table_td"] = ParagraphStyle(
        "table_td", parent=base["BodyText"], fontName="Helvetica",
        fontSize=9, leading=12, textColor=CHARCOAL,
    )
    s["table_td_rank"] = ParagraphStyle(
        "table_td_rank", parent=base["BodyText"], fontName="Helvetica-Bold",
        fontSize=10, leading=12, textColor=GOLD_DARK, alignment=1,
    )
    s["table_td_value"] = ParagraphStyle(
        "table_td_value", parent=base["BodyText"], fontName="Helvetica-Bold",
        fontSize=10, leading=12, textColor=CHARCOAL, alignment=2,
    )
    s["qr_caption"] = ParagraphStyle(
        "qr_caption", parent=base["BodyText"], fontName="Helvetica",
        fontSize=6.5, leading=8, textColor=MUTED_LIGHT, alignment=1,
    )
    return s


def _result_color(status: str | None) -> colors.Color:
    if not status:
        return MUTED
    up = status.upper()
    if "ELEITO" in up or "MEDIA" in up:
        return GREEN
    if "SUPLENTE" in up:
        return AMBER
    if "NAO ELEITO" in up or "NÃO ELEITO" in up or "REJEIT" in up:
        return RED
    return MUTED


# -------------------------------------------------- bar flowable
class BarFlowable(Flowable):
    """Barra horizontal proporcional pra rankings."""

    def __init__(
        self,
        value: int,
        max_value: int,
        width: float,
        height: float = 5,
        color=GOLD,
        track=CREAM_DARK,
    ):
        super().__init__()
        self.value = value
        self.max_value = max(1, max_value)
        self.width = width
        self.height = height
        self.color = color
        self.track = track

    def wrap(self, *_):
        return (self.width, self.height)

    def draw(self):
        c = self.canv
        c.setFillColor(self.track)
        c.roundRect(0, 0, self.width, self.height, self.height / 2, stroke=0, fill=1)
        pct = max(0.02, min(1.0, self.value / self.max_value))
        c.setFillColor(self.color)
        c.roundRect(0, 0, self.width * pct, self.height, self.height / 2, stroke=0, fill=1)


# -------------------------------------------------- mini-mapa do Brasil
# Polygon simplificado do Brasil (lat, lng). ~30 pontos.
BR_OUTLINE = [
    (5.27, -60.74), (4.45, -51.32), (1.71, -50.36), (-0.97, -47.32),
    (-2.81, -44.30), (-5.16, -39.50), (-7.32, -34.79), (-9.55, -35.27),
    (-12.97, -38.50), (-15.78, -39.05), (-18.91, -39.81), (-22.90, -41.99),
    (-23.49, -45.32), (-25.43, -48.55), (-28.30, -48.65), (-30.03, -50.20),
    (-31.77, -52.34), (-33.69, -53.38), (-32.34, -55.18), (-30.91, -55.55),
    (-29.16, -56.55), (-27.55, -55.56), (-25.30, -54.59), (-22.10, -54.45),
    (-19.55, -57.78), (-15.86, -60.18), (-11.04, -65.32), (-9.50, -67.90),
    (-7.13, -73.66), (-2.16, -69.96), (0.96, -69.51), (1.32, -64.84),
    (4.40, -60.46),
]


class MiniBrazilMap(Flowable):
    """Outline simplificado do Brasil com bolhas dos municipios em dourado."""

    def __init__(
        self,
        coords: Iterable[tuple[float, float, int]],  # (lat, lng, votes)
        width: float = 5.5 * cm,
        height: float = 5.0 * cm,
    ):
        super().__init__()
        self.coords = list(coords)
        self.width = width
        self.height = height

    def wrap(self, *_):
        return (self.width, self.height)

    def _to_xy(self, lat: float, lng: float) -> tuple[float, float]:
        # Bounding box do Brasil
        LAT_MIN, LAT_MAX = -34.0, 6.0
        LNG_MIN, LNG_MAX = -74.5, -33.5
        x = (lng - LNG_MIN) / (LNG_MAX - LNG_MIN) * self.width
        y = (lat - LAT_MIN) / (LAT_MAX - LAT_MIN) * self.height
        return x, y

    def draw(self):
        c = self.canv
        # Outline
        c.setStrokeColor(CHAMPAGNE)
        c.setFillColor(CHARCOAL_3)
        c.setLineWidth(0.6)
        path = c.beginPath()
        for i, (lat, lng) in enumerate(BR_OUTLINE):
            x, y = self._to_xy(lat, lng)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.close()
        c.drawPath(path, stroke=1, fill=1)
        # Pontos
        if not self.coords:
            return
        max_v = max((v for _, _, v in self.coords), default=1)
        for lat, lng, v in self.coords:
            if lat is None or lng is None:
                continue
            x, y = self._to_xy(lat, lng)
            pct = v / max(1, max_v)
            r = max(1.2, 1.5 + pct * 4)
            c.setFillColor(GOLD)
            c.setStrokeColor(WHITE)
            c.setLineWidth(0.3)
            c.circle(x, y, r, stroke=1, fill=1)


# -------------------------------------------------- pie chart de votos por UF
def _votes_pie(uf_votes: dict[str, int], width: float = 13 * cm, height: float = 5.5 * cm) -> Drawing:
    """Pie chart top 5 UFs + Outros, com legenda lateral."""
    items = sorted(uf_votes.items(), key=lambda kv: kv[1], reverse=True)
    if len(items) > 5:
        top = items[:5]
        other = sum(v for _, v in items[5:])
        top.append(("Outros", other))
        items = top
    total = sum(v for _, v in items) or 1
    labels = [f"{uf} · {round(v / total * 100):d}%" for uf, v in items]
    data = [v for _, v in items]

    d = Drawing(width, height)
    pie = Pie()
    pie.x = 10
    pie.y = (height - 4 * cm) / 2
    pie.width = 4 * cm
    pie.height = 4 * cm
    pie.data = data
    pie.labels = None
    pie.slices.strokeColor = WHITE
    pie.slices.strokeWidth = 1
    for i in range(len(data)):
        pie.slices[i].fillColor = PIE_PALETTE[i % len(PIE_PALETTE)]
    pie.sideLabels = 0
    pie.simpleLabels = 1
    d.add(pie)

    # Legenda lateral
    leg = Legend()
    leg.alignment = "right"
    leg.x = 4.7 * cm
    leg.y = height - 1 * cm
    leg.deltay = 14
    leg.fontName = "Helvetica"
    leg.fontSize = 9
    leg.boxAnchor = "nw"
    leg.columnMaximum = 8
    leg.strokeColor = None
    leg.strokeWidth = 0
    leg.dxTextSpace = 6
    leg.dy = 8
    leg.dx = 8
    leg.colorNamePairs = [
        (PIE_PALETTE[i % len(PIE_PALETTE)], labels[i]) for i in range(len(data))
    ]
    d.add(leg)
    return d


# -------------------------------------------------- QR code helper
def _make_qr_image(url: str, size_cm: float = 2.4) -> Image | None:
    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=4,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#1B1714", back_color="#FFFFFF").convert("RGB")
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return Image(buf, width=size_cm * cm, height=size_cm * cm)
    except Exception:
        return None


# -------------------------------------------------- page canvases
def _cover_page(canvas, doc):
    w, h = A4
    canvas.saveState()
    canvas.setFillColor(CHARCOAL)
    canvas.rect(0, 0, w, h, stroke=0, fill=1)
    # Detalhe diagonal sutil — ornamento editorial.
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(0.4)
    canvas.line(2 * cm, h - 2 * cm, w / 2 - 2.5 * cm, h - 2 * cm)
    canvas.line(w / 2 + 2.5 * cm, h - 2 * cm, w - 2 * cm, h - 2 * cm)
    canvas.line(2 * cm, 2 * cm, w / 2 - 2.5 * cm, 2 * cm)
    canvas.line(w / 2 + 2.5 * cm, 2 * cm, w - 2 * cm, 2 * cm)
    # Faixas finas
    canvas.setFillColor(GOLD)
    canvas.rect(0, h - 6, w, 6, stroke=0, fill=1)
    canvas.rect(0, 0, w, 6, stroke=0, fill=1)
    canvas.restoreState()


def _inner_page(canvas, doc):
    w, h = A4
    canvas.saveState()
    # Faixa fina dourada superior
    canvas.setFillColor(GOLD)
    canvas.rect(0, h - 6, w, 6, stroke=0, fill=1)
    # Rodape branded
    canvas.setFillColor(CHARCOAL)
    canvas.rect(0, 0, w, 18, stroke=0, fill=1)
    canvas.setFillColor(GOLD)
    canvas.rect(0, 18, w, 1, stroke=0, fill=1)
    canvas.setFillColor(GOLD)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(2 * cm, 6, "MARENOSTRUM")
    canvas.setFillColor(CREAM)
    canvas.setFont("Helvetica", 7)
    canvas.drawCentredString(w / 2, 6, f"Dossie eleitoral · {doc.page:02d}")
    canvas.drawRightString(w - 2 * cm, 6, "Dados publicos TSE")
    canvas.restoreState()


# -------------------------------------------------- builder
def build_candidate_dossier(
    *,
    candidate_name: str,
    urn_name: str,
    number: int,
    office_name: str,
    state: str,
    year: int,
    result_status: str | None,
    party_abbr: str,
    party_name: str,
    party_number: int,
    total_votes: int,
    muni_count: int,
    assets_total: float | None,
    revenue_total: float | None,
    expense_total: float | None,
    social_links: dict | list | None,
    municipality_results: Iterable[tuple[str, str, int]],
    zone_results: Iterable[tuple[int, str, str, int]],
    photo_bytes: bytes | None = None,
    # NOVO v2
    candidate_id: str | None = None,
    public_url_base: str | None = None,
    municipality_coords: Iterable[tuple[float | None, float | None, int]] | None = None,
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.2 * cm,
        rightMargin=2.2 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title=f"Dossie - {urn_name}",
        author="MareNostrum",
        subject=f"Dossie eleitoral - {office_name} {year} - {state}",
    )
    st = _styles()
    flow: list = []

    # ============ PAG 1 — CAPA ============
    flow.append(Spacer(1, 1.4 * cm))
    flow.append(Paragraph("D O S S I E   E L E I T O R A L", st["cover_kicker"]))
    flow.append(Spacer(1, 0.7 * cm))

    # Foto centralizada
    if photo_bytes:
        try:
            img = Image(BytesIO(photo_bytes), width=4.6 * cm, height=6.0 * cm)
            photo_tbl = Table(
                [[img]],
                colWidths=[5.0 * cm],
                rowHeights=[6.4 * cm],
                hAlign="CENTER",
            )
            photo_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), CHARCOAL_2),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 1.2, GOLD),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]))
            flow.append(photo_tbl)
        except Exception:
            flow.append(Spacer(1, 6.4 * cm))
    else:
        initial = (urn_name or "?")[0].upper()
        ph = Paragraph(
            f'<font color="#C9A24B" size="44"><b>{initial}</b></font>',
            ParagraphStyle("ph", alignment=1, leading=56),
        )
        photo_tbl = Table(
            [[ph]],
            colWidths=[5.0 * cm],
            rowHeights=[6.4 * cm],
            hAlign="CENTER",
        )
        photo_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), CHARCOAL_2),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 1.2, GOLD),
        ]))
        flow.append(photo_tbl)

    flow.append(Spacer(1, 0.8 * cm))
    flow.append(Paragraph(urn_name.upper(), st["cover_name"]))
    if candidate_name and candidate_name != urn_name:
        flow.append(Paragraph(candidate_name, st["cover_legal"]))
    flow.append(Spacer(1, 0.35 * cm))

    chip_line = (
        f'<font color="#E8D5A0">{office_name.upper()}</font>'
        f'  <font color="#6E6358">•</font>  '
        f'<font color="#C9A24B">{state}</font>'
        f'  <font color="#6E6358">•</font>  '
        f'<font color="#E8D5A0">{year}</font>'
    )
    flow.append(Paragraph(chip_line, st["cover_meta"]))
    party_line = (
        f'<font color="#FAF6EC" size="11"><b>{party_abbr}</b></font>'
        f'<font color="#A39785" size="10"> · {party_number} · {party_name}</font>'
    )
    flow.append(Paragraph(party_line, st["cover_meta"]))
    flow.append(Spacer(1, 0.55 * cm))

    badge_color = _result_color(result_status)
    badge_text = (result_status or "—").upper()
    badge_tbl = Table(
        [[Paragraph(badge_text, st["badge_cover"])]],
        colWidths=[6.5 * cm],
        hAlign="CENTER",
    )
    badge_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), badge_color),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    flow.append(badge_tbl)

    # Bottom: mini-map (esquerda) + QR (direita)
    coords = list(municipality_coords or [])
    has_coords = any(c[0] is not None and c[1] is not None for c in coords)
    qr_url = (
        f"{public_url_base.rstrip('/')}/dashboard/analises/candidato/{candidate_id}"
        if (public_url_base and candidate_id)
        else None
    )
    qr_img = _make_qr_image(qr_url, size_cm=2.2) if qr_url else None

    flow.append(Spacer(1, 1.0 * cm))

    bottom_left = []
    bottom_right = []
    if has_coords:
        bottom_left.append(MiniBrazilMap(coords, width=5.0 * cm, height=4.4 * cm))
        bottom_left.append(Spacer(1, 4))
        bottom_left.append(Paragraph(
            f'<font color="#A39785">{_fmt_int(len(coords))} municipios votados</font>',
            st["qr_caption"],
        ))
    if qr_img:
        bottom_right.append(qr_img)
        bottom_right.append(Spacer(1, 4))
        bottom_right.append(Paragraph(
            '<font color="#A39785">Versao online completa</font>',
            st["qr_caption"],
        ))

    if bottom_left or bottom_right:
        # Tabela 3 colunas: map · brand · qr
        brand = [
            Spacer(1, 0.5 * cm),
            Paragraph("M A R E N O S T R U M", st["cover_brand"]),
            Spacer(1, 2),
            Paragraph("INTELIGENCIA POLITICA E ELEITORAL", st["cover_brand_sub"]),
        ]
        cells_row = [
            bottom_left if bottom_left else [Spacer(1, 1)],
            brand,
            bottom_right if bottom_right else [Spacer(1, 1)],
        ]
        bottom = Table(
            [cells_row],
            colWidths=[6 * cm, 5 * cm, 6 * cm],
        )
        bottom.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ]))
        flow.append(bottom)
    else:
        flow.append(Spacer(1, 1.5 * cm))
        flow.append(Paragraph("M A R E N O S T R U M", st["cover_brand"]))
        flow.append(Spacer(1, 0.1 * cm))
        flow.append(Paragraph("INTELIGENCIA POLITICA E ELEITORAL", st["cover_brand_sub"]))

    flow.append(PageBreak())

    # ============ PAG 2 — SUMARIO ============
    has_muni = bool(list(municipality_results))
    has_zone = bool(list(zone_results))
    # Reseta os iteradores
    muni_rows = list(municipality_results)
    zone_rows = list(zone_results)

    flow.append(Spacer(1, 1.5 * cm))
    flow.append(Paragraph("CONTEUDO", st["toc_title"]))
    flow.append(Paragraph("Sumario", st["toc_h2"]))

    toc_entries = [("Visao geral", "03"), ("Perfil patrimonial e financeiro", "03")]
    page_cursor = 4
    if muni_rows:
        toc_entries.append(("Votos por municipio · top 50", f"{page_cursor:02d}"))
        page_cursor += 1
        if len(muni_rows) > 25:
            page_cursor += 1  # provavelmente 2 paginas
    if zone_rows:
        toc_entries.append(("Votos por zona eleitoral · top 30", f"{page_cursor:02d}"))

    toc_cells = []
    for title, pageno in toc_entries:
        toc_cells.append([
            Paragraph(title, st["toc_item"]),
            Paragraph(pageno, st["toc_page"]),
        ])
    toc = Table(toc_cells, colWidths=[12.5 * cm, 4 * cm])
    toc.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
    ]))
    flow.append(toc)

    flow.append(Spacer(1, 1 * cm))
    flow.append(Paragraph(
        f'<font color="#6E6358"><i>Candidato: <b>{urn_name}</b> · {office_name} · '
        f'{state} · {year}</i></font>',
        st["body"],
    ))

    flow.append(PageBreak())

    # ============ PAG 3 — VISAO GERAL ============
    flow.append(Spacer(1, 0.2 * cm))
    flow.append(Paragraph("VISAO GERAL", st["section"]))
    flow.append(Paragraph(
        f"{urn_name}",
        st["h2"],
    ))
    flow.append(Paragraph(
        f"{office_name} · {state} · {year}",
        st["sub"],
    ))

    stat_cells = [
        [
            Paragraph(_fmt_int(total_votes), st["stat_value"]),
            Paragraph(_fmt_int(muni_count), st["stat_value"]),
        ],
        [
            Paragraph("VOTOS NOMINAIS", st["stat_label"]),
            Paragraph("MUNICIPIOS COM VOTOS", st["stat_label"]),
        ],
    ]
    stats = Table(stat_cells, colWidths=[8.1 * cm, 8.1 * cm])
    stats.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), CREAM),
        ("BACKGROUND", (1, 0), (1, -1), CREAM_DARK),
        ("LINEABOVE", (0, 0), (-1, 0), 2, GOLD),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 14),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
    ]))
    flow.append(stats)

    # Pizza UF (se muni_rows tem mais de 1 UF)
    uf_votes: Counter = Counter()
    for _, uf, v in muni_rows:
        uf_votes[uf] += v
    if len(uf_votes) >= 2:
        flow.append(Spacer(1, 18))
        flow.append(Paragraph("DISTRIBUICAO POR UF", st["section"]))
        flow.append(_votes_pie(dict(uf_votes)))

    # Perfil rico
    has_profile = any(
        v is not None for v in (assets_total, revenue_total, expense_total)
    )
    if has_profile:
        flow.append(Spacer(1, 16))
        flow.append(Paragraph("PERFIL PATRIMONIAL E FINANCEIRO", st["section"]))
        prof_cells = [
            [
                Paragraph(_fmt_brl(assets_total), st["stat_value_small"]),
                Paragraph(_fmt_brl(revenue_total), st["stat_value_small"]),
                Paragraph(_fmt_brl(expense_total), st["stat_value_small"]),
            ],
            [
                Paragraph("PATRIMONIO DECLARADO", st["stat_label"]),
                Paragraph("RECEITAS DE CAMPANHA", st["stat_label"]),
                Paragraph("DESPESAS DE CAMPANHA", st["stat_label"]),
            ],
        ]
        prof = Table(prof_cells, colWidths=[5.4 * cm, 5.4 * cm, 5.4 * cm])
        prof.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), CREAM),
            ("LINEABOVE", (0, 0), (-1, 0), 2, GOLD),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
            ("TOPPADDING", (0, 1), (-1, 1), 0),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
            ("LINEAFTER", (0, 0), (0, -1), 0.5, BORDER),
            ("LINEAFTER", (1, 0), (1, -1), 0.5, BORDER),
        ]))
        flow.append(prof)

    if social_links:
        items: list[str] = []
        if isinstance(social_links, dict):
            for k, v in social_links.items():
                if v:
                    items.append(f'<b><font color="#8C6E2A">{k.upper()}</font></b> {v}')
        elif isinstance(social_links, list):
            for v in social_links:
                if v:
                    items.append(str(v))
        if items:
            flow.append(Spacer(1, 14))
            flow.append(Paragraph("PRESENCA DIGITAL", st["section"]))
            flow.append(Paragraph(
                ' &nbsp;·&nbsp; '.join(items), st["body"],
            ))

    # ============ TOP MUNICIPIOS ============
    if muni_rows:
        flow.append(PageBreak())
        flow.append(Spacer(1, 0.2 * cm))
        flow.append(Paragraph("VOTOS POR MUNICIPIO", st["section"]))
        flow.append(Paragraph("Top 50 cidades por votos", st["h2"]))
        flow.append(Spacer(1, 6))

        bar_w = 4.5 * cm
        top_n = muni_rows[:50]
        max_v = max((v for _, _, v in top_n), default=1)
        data: list[list] = [[
            Paragraph("#", st["table_th"]),
            Paragraph("MUNICIPIO", st["table_th"]),
            Paragraph("UF", st["table_th"]),
            Paragraph("", st["table_th"]),
            Paragraph("VOTOS", st["table_th"]),
        ]]
        for i, (mname, uf, votes) in enumerate(top_n, start=1):
            data.append([
                Paragraph(f"{i}", st["table_td_rank"]),
                Paragraph(mname, st["table_td"]),
                Paragraph(uf, st["table_td"]),
                BarFlowable(votes, max_v, bar_w),
                Paragraph(_fmt_int(votes), st["table_td_value"]),
            ])
        tbl = Table(
            data,
            colWidths=[0.8 * cm, 5.5 * cm, 0.9 * cm, bar_w + 0.2 * cm, 2.4 * cm],
            repeatRows=1,
        )
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), CHARCOAL),
            ("LEFTPADDING", (0, 0), (-1, 0), 8),
            ("RIGHTPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 7),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, CREAM]),
            ("LEFTPADDING", (0, 1), (-1, -1), 8),
            ("RIGHTPADDING", (0, 1), (-1, -1), 8),
            ("TOPPADDING", (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, 0), 1, GOLD),
            ("ALIGN", (0, 1), (0, -1), "CENTER"),
            ("ALIGN", (2, 1), (2, -1), "CENTER"),
        ]))
        flow.append(tbl)
        if len(muni_rows) > 50:
            flow.append(Spacer(1, 6))
            flow.append(Paragraph(
                f"<i>+ {_fmt_int(len(muni_rows) - 50)} outros municipios com votos.</i>",
                st["small"],
            ))

    # ============ TOP ZONAS ============
    if zone_rows:
        flow.append(PageBreak())
        flow.append(Spacer(1, 0.2 * cm))
        flow.append(Paragraph("VOTOS POR ZONA ELEITORAL", st["section"]))
        flow.append(Paragraph("Top 30 zonas por votos", st["h2"]))
        flow.append(Spacer(1, 6))

        bar_w = 4.2 * cm
        top_n = zone_rows[:30]
        max_v = max((v for _, _, _, v in top_n), default=1)
        data = [[
            Paragraph("#", st["table_th"]),
            Paragraph("ZONA", st["table_th"]),
            Paragraph("MUNICIPIO", st["table_th"]),
            Paragraph("UF", st["table_th"]),
            Paragraph("", st["table_th"]),
            Paragraph("VOTOS", st["table_th"]),
        ]]
        for i, (zone, mname, uf, votes) in enumerate(top_n, start=1):
            data.append([
                Paragraph(f"{i}", st["table_td_rank"]),
                Paragraph(str(zone), st["table_td"]),
                Paragraph(mname, st["table_td"]),
                Paragraph(uf, st["table_td"]),
                BarFlowable(votes, max_v, bar_w),
                Paragraph(_fmt_int(votes), st["table_td_value"]),
            ])
        tbl = Table(
            data,
            colWidths=[0.8 * cm, 1.2 * cm, 5.0 * cm, 0.9 * cm, bar_w + 0.2 * cm, 2.0 * cm],
            repeatRows=1,
        )
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), CHARCOAL),
            ("LEFTPADDING", (0, 0), (-1, 0), 8),
            ("RIGHTPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 7),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, CREAM]),
            ("LEFTPADDING", (0, 1), (-1, -1), 8),
            ("RIGHTPADDING", (0, 1), (-1, -1), 8),
            ("TOPPADDING", (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, 0), 1, GOLD),
            ("ALIGN", (0, 1), (0, -1), "CENTER"),
            ("ALIGN", (1, 1), (1, -1), "CENTER"),
            ("ALIGN", (3, 1), (3, -1), "CENTER"),
        ]))
        flow.append(tbl)

    flow.append(Spacer(1, 16))
    flow.append(Paragraph(
        '<i>Documento gerado automaticamente pela plataforma MareNostrum a partir '
        'de dados publicos do Tribunal Superior Eleitoral (TSE). Patrimonio, receitas '
        'e despesas sao declarados pelo proprio candidato.</i>',
        st["small"],
    ))

    doc.build(flow, onFirstPage=_cover_page, onLaterPages=_inner_page)
    return buf.getvalue()
