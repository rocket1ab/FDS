#!/usr/bin/env python3
"""Update section 6 DDA tables in the retained aircraft assessment DOCX."""

from __future__ import annotations

import argparse
import shutil
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt


ANGLE_ROWS = [
    ["el=15°", "1,912", "1,250", "735"],
    ["el=30°", "1,434", "1,100", "647"],
    ["el=45°", "1,344", "900", "529"],
]

MATERIAL_ROWS = [
    ["RADM 雷达罩（玻璃纤维）", "✓", "386", "735"],
    ["WINS 舷窗（PMMA）", "✓", "213", "677"],
    ["BED 床垫（尼龙）", "✓", "99", "441"],
    ["CURT 窗帘（尼龙）", "✓", "267", "618"],
    ["U4 设备", "—", "0", "0"],
    ["SEAT 座椅（聚氨酯泡沫）", "✓", "92", "618"],
    ["AL2024 机体蒙皮", "✓", "674", "735"],
    ["AL5052 管道", "—", "0", "0"],
    ["AL7075 机体框架", "✓", "121", "735"],
    ["O2TANK 氧气瓶", "✓", "10", "529"],
    ["H1 导航子系统（6061铝合金）", "✓", "5", "735"],
    ["H2 任务子系统（6061铝合金）", "✓", "37", "735"],
    ["H3 显示子系统（6061铝合金）", "—", "0", "0"],
    ["H4 通信子系统（6061铝合金）", "✓", "4", "118"],
    ["H5 电池（6061铝合金）", "✓", "4", "618"],
    ["H6 电力传输子系统（PVC）", "—", "0", "0"],
    ["H7 操纵子系统（CR橡胶）", "—", "0", "0"],
]


def set_cell_text(cell, text: str, *, bold: bool = False, size: float = 8.5) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.name = "宋体"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    run.font.size = Pt(size)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER


def repeat_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def prevent_row_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    cant_split = OxmlElement("w:cantSplit")
    tr_pr.append(cant_split)


def fill_table(table, headers: list[str], rows: list[list[str]], font_size: float) -> None:
    while len(table.rows) < len(rows) + 1:
        table.add_row()
    while len(table.rows) > len(rows) + 1:
        table._tbl.remove(table.rows[-1]._tr)
    for col, text in enumerate(headers):
        set_cell_text(table.rows[0].cells[col], text, bold=True, size=font_size)
    repeat_header(table.rows[0])
    for row_index, values in enumerate(rows, start=1):
        prevent_row_split(table.rows[row_index])
        for col, text in enumerate(values):
            set_cell_text(table.rows[row_index].cells[col], text, size=font_size)


def insert_paragraph_before_table(document: Document, table, text: str, style: str = "Body Text"):
    paragraph = document.add_paragraph(style=style)
    paragraph.add_run(text)
    table._tbl.addprevious(paragraph._p)
    return paragraph


def style_added_paragraph(paragraph, size: float = 9.5) -> None:
    paragraph.paragraph_format.space_before = Pt(3)
    paragraph.paragraph_format.space_after = Pt(5)
    for run in paragraph.runs:
        run.font.name = "宋体"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        run.font.size = Pt(size)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("docx", type=Path)
    args = parser.parse_args()
    source = args.docx.resolve()
    document = Document(source)

    angle_table = document.tables[15]
    material_table = document.tables[16]
    fill_table(
        angle_table,
        ["角度", "DDA受照体素面数", "基准峰值\n(E₀=1287 kW/m²)", "Q=50归一化峰值\n(kW/m²)"],
        ANGLE_ROWS,
        8.5,
    )
    fill_table(
        material_table,
        ["材料/设备组", "EXTERNAL_FLUX变体", "受照面数", "Q=50峰值\n(kW/m²)"],
        MATERIAL_ROWS,
        8.0,
    )

    heading_62 = next(p for p in document.paragraphs if p.text.strip() == "6.2 各材料受照分析")
    normalization = heading_62.insert_paragraph_before(
        "Q=50 J/cm²、W=100 kt时，NUCLEAR_RAMP积分为0.660398 s，入射平面峰值热流为757.1 kW/m²。"
        "Q=50局部峰值按入射平面光冲量归一化；el=15°、30°和45°对应的最大局部积分光冲量分别为"
        "48.5、42.7和34.9 J/cm²。",
        style="Body Text",
    )
    style_added_paragraph(normalization)

    intro = insert_paragraph_before_table(
        document,
        material_table,
        "以下结果对应az=270°、el=15°、Q=50 J/cm²。受照面数为DDA判定具有直达视线且写入"
        "EXTERNAL_FLUX的0.1 m体素面数量。",
    )
    style_added_paragraph(intro)

    old_note = next(p for p in document.paragraphs if "AL_FLUX_MAP" in p.text and "vendor" in p.text)
    old_note.text = (
        "说明：新版体素流程已为AL2024、AL7075、H1-H5等铝合金表面生成EXTERNAL_FLUX变体，"
        "旧版“铝表面未赋热流”问题已修复。表中0受照面表示设备在az=270°、el=15°下被几何遮挡、"
        "没有直达外部辐射；其材料属性仍保留，并可通过舱内火焰、热烟气和二次辐射升温。"
    )
    style_added_paragraph(old_note, 9.0)

    for paragraph in document.paragraphs:
        if paragraph is old_note:
            continue
        if "铝 EXTERNAL_FLUX 基座未生成" in paragraph.text:
            paragraph.text = (
                "铝合金外部热流赋值已修复：新版DDA体素流程已为AL2024、AL7075及H1-H5生成"
                "EXTERNAL_FLUX变体；后续角度比较均应采用Q归一化后的新版结果。"
            )
            style_added_paragraph(paragraph)

    temp = source.with_name(source.stem + ".section6.tmp.docx")
    document.save(temp)
    shutil.copy2(temp, source)
    temp.unlink()
    print(source)


if __name__ == "__main__":
    main()
