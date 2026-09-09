"""
expand_report_ppt.py — 在用户已装饰的汇报 PPT 上追加 5 页深度内容并重排页序
不改动既有 15 页的任何形状；新页使用与现有页面相同的版式。
15 页 → 20 页。
"""
import copy
import os

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "华科蓝_第一次汇报_基于UDP的AR实时图传.pptx")
prs = Presentation(SRC)
assert len(prs.slides._sldIdLst) == 15, "页数异常，请确认文件版本"

LAYOUT = prs.slides[0].slide_layout          # 与现有页面同版式
BLUE = RGBColor(0x1F, 0x4E, 0x79)
ORANGE = RGBColor(0xE6, 0x7D, 0x23)
DARK = RGBColor(0x33, 0x33, 0x33)
GREY = RGBColor(0x66, 0x66, 0x66)
CARD_BG = RGBColor(0xF5, 0xF9, 0xFD)
SOFT = RGBColor(0xE8, 0xF2, 0xFC)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "微软雅黑"


def txt(slide, x, y, w, h, text, size=16, color=DARK, bold=False,
        align=PP_ALIGN.LEFT, spacing=1.05):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text.split("\n")[0]
    p.font.name = FONT
    p.font.size = Pt(size)
    p.font.bold = bold
    p.font.color.rgb = color
    p.alignment = align
    for line in text.split("\n")[1:]:
        p2 = tf.add_paragraph()
        p2.text = line
        p2.font.name = FONT
        p2.font.size = Pt(size)
        p2.font.bold = bold
        p2.font.color.rgb = color
        p2.alignment = align
        p2.line_spacing = spacing
    return box


def rect(slide, x, y, w, h, fill, line=None,
         shape=MSO_SHAPE.ROUNDED_RECTANGLE):
    sh = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w),
                                Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(1.5)
    sh.shadow.inherit = False
    return sh


def badge(slide, x, y, d, text, fill=ORANGE, size=14):
    c = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y),
                               Inches(d), Inches(d))
    c.fill.solid()
    c.fill.fore_color.rgb = fill
    c.line.fill.background()
    c.shadow.inherit = False
    tf = c.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.text = text
    p.font.name = "Arial"
    p.font.size = Pt(size)
    p.font.bold = True
    p.font.color.rgb = WHITE
    p.alignment = PP_ALIGN.CENTER


def card(slide, x, y, w, h, tag, head, lines, color=BLUE, body=13.5,
         head_size=16):
    rect(slide, x, y, w, h, CARD_BG, color)
    if tag:
        badge(slide, x + 0.16, y + 0.16, 0.52, tag, color, 13)
        tx = x + 0.82
    else:
        tx = x + 0.2
    txt(slide, tx, y + 0.18, w - (tx - x) - 0.15, 0.45, head, head_size,
        color, True)
    if lines:
        txt(slide, x + 0.22, y + 0.75, w - 0.44, h - 0.9,
            "\n".join(lines), body, DARK)


def header(slide, num, title, eng=""):
    txt(slide, 0.7, 0.32, 11.9, 0.6, num + "  " + title, 27, BLUE, True)
    if eng:
        txt(slide, 0.73, 0.98, 11.9, 0.3, eng, 11, GREY)
    rect(slide, 0.73, 1.28, 1.5, 0.045, ORANGE, shape=MSO_SHAPE.RECTANGLE)


def pageno(slide, n):
    txt(slide, 12.35, 7.05, 0.7, 0.3, "%02d" % n, 11, GREY, False,
        PP_ALIGN.RIGHT)


def arrow(slide, x, y, w=0.5, h=0.32):
    a = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x), Inches(y),
                               Inches(w), Inches(h))
    a.fill.solid()
    a.fill.fore_color.rgb = ORANGE
    a.line.fill.background()
    a.shadow.inherit = False


slides = list(prs.slides)


def add_page(pos_num, title, eng=""):
    s = prs.slides.add_slide(LAYOUT)
    for ph in list(s.placeholders):
        ph._element.getparent().remove(ph._element)
    header(s, title, eng)
    pageno(s, pos_num)
    return s


# ---- NEW A：传输层选型（插到“需求分析”之后） ----
s = add_page(5, "传输层选型：UDP vs TCP")
card(s, 0.75, 1.55, 5.6, 2.5, "U", "UDP（用户数据报）", [
    "无连接 · 8B 头 · 有报文边界",
    "尽力而为：不保证到达与顺序",
    "实测 19.64 fps · 3.95 ms"], BLUE, 14, 16)
card(s, 6.95, 1.55, 5.6, 2.5, "T", "TCP（传输控制）", [
    "面向连接 · 可靠有序 字节流",
    "重传/流控/拥塞控制 · 需处理粘包",
    "实测 19.51 fps · 完整但可卡顿"], ORANGE, 14, 16)
rect(s, 0.75, 4.35, 11.8, 0.8, SOFT, BLUE)
txt(s, 0.75, 4.5, 11.8, 0.5,
    "选型结论：实时视频“要新不要全”→ UDP + 应用层补偿；"
    "TCP 的可靠以可能阻塞后续数据为代价", 15.5, BLUE, True,
    PP_ALIGN.CENTER)
card(s, 0.75, 5.35, 11.8, 1.55, "计网视角", "三个标准协议观察点", [
    "端口复用：9500 图传 / 9501 字幕 —— 一台主机两个 Socket 并行服务",
    "字节流粘包：TCP 无消息边界 → 4B 长度前缀定长分帧（工程标配）",
    "拥塞控制权衡：丢包触发降速保护网络，但与实时性需求天然冲突"],
    ORANGE, 13.5, 15)

# ---- NEW B：GTP 三大机制（插到“实验验证”之前） ----
s = prs.slides.add_slide(LAYOUT)
for ph in list(s.placeholders):
    ph._element.getparent().remove(ph._element)
header(s, "05", "关键机制：让“不可靠”变成“可用”", "MECHANISMS")
pageno(s, 10)
mech = [("帧级超时丢弃", [
    "每帧独立 0.5s 超时窗口",
    "未收齐 → 整帧丢弃，绝不等待",
    "丢包影响被锁定在单帧之内"], BLUE),
    ("增量节流上报", [
        "变化 ≥ 2 才真实发包",
        "静默期 5s 兜底一次",
        "平稳带宽，避免流量尖峰"], ORANGE),
    ("端到端时延测量", [
        "帧头写入封装时刻",
        "接收端即时差值",
        "实测 < 4 ms 可持续观测"], BLUE),
    ("双重完整性校验", [
        "CRC16 拦截传输误码",
        "长度一致性兜底",
        "重算 CRC 的对抗也检出"], ORANGE)]
for i, (head, lines, color) in enumerate(mech):
    x = 0.75 + (i % 2) * 6.1
    y = 1.55 + (i // 2) * 2.45
    card(s, x, y, 5.85, 2.2, "", head, lines, color, 14, 16)
txt(s, 0.75, 6.3, 11.8, 0.45,
    "四个机制合起来回答科学问题：不可靠信道上，“要新不要全”是可实现的工程策略",
    16, BLUE, True, PP_ALIGN.CENTER)

# ---- NEW C：结果分析（插到“实验数据”之后） ----
s = prs.slides.add_slide(LAYOUT)
for ph in list(s.placeholders):
    ph._element.getparent().remove(ph._element)
header(s, "07", "结果分析：数字背后的机理", "ANALYSIS")
card(s, 0.75, 1.55, 11.8, 1.9, "①", "为什么 50% 丢包 ≈ 帧率减半", [
    "丢包独立随机作用于每个数据报 → 完整帧比例期望 = (1-p)",
    "理论 20×0.5 = 10 fps，实测 9.56 fps —— 与期望高度吻合，模型可信"],
    BLUE, 14, 16)
card(s, 0.75, 3.7, 11.8, 1.9, "②", "TCP 为什么会卡顿", [
    "重传期间，后续已到达的字节无法交付（队头阻塞）",
    "公网劣化时重传频发 → 播放连续性中断，这正是实时场景的致命伤"],
    ORANGE, 14, 16)
card(s, 0.75, 5.85, 11.8, 1.3, "③", "恢复能力对比", [
    "UDP：丢一帧只黑一瞬，下一帧立即续播；TCP：恢复时长取决于重传往返",
    "结论：实时视频的“卡顿感”主要来自等待，而不是数据丢失本身"],
    BLUE, 14, 16)

# ---- NEW D：计网知识②（插到“计网知识①”之后） ----
s = prs.slides.add_slide(LAYOUT)
for ph in list(s.placeholders):
    ph._element.getparent().remove(ph._element)
header(s, "08", "计网知识② 端口 · 粘包 · RPA", "NETWORKING II")
kn2 = [("端口与 Socket", "IP 定位主机，端口定位进程",
        "9500 图传 · 9501 字幕 · 9600 中继 · 443 GLM API"),
       ("TCP 粘包处理", "字节流无边界，需自定义消息边界",
        "4B 长度前缀定长分帧：先读长度，再精确读满"),
       ("RPA 地址轮换", "绑定设备防追踪：地址每 15 分钟轮换",
        "广播不含名称，仅绑定手机可解析（IRK）"),
       ("白名单直连", "断连后只发定向广播给已配对手机",
        "对第三方设备完全隐身 —— 生态墙的协议层根源")]
for i, (a, b, c) in enumerate(kn2):
    y = 1.6 + i * 1.3
    badge(s, 1.2, y, 0.55, "%02d" % (i + 1),
          BLUE if i % 2 == 0 else ORANGE, 13)
    txt(s, 2.0, y - 0.04, 4.0, 0.45, a, 15.5, DARK, True)
    txt(s, 6.1, y + 0.02, 6.3, 0.75, c, 12.5, GREY)

# ---- NEW E：踩坑实录（插到“计网知识②”之后） ----
s = prs.slides.add_slide(LAYOUT)
for ph in list(s.placeholders):
    ph._element.getparent().remove(ph._element)
header(s, "09", "踩坑实录：三个真实的工程问题", "DEBUG LOG")
pits = [("坑1", "imshow 报“函数未实现”", [
    "根因：headless 版 OpenCV 覆盖了 GUI 版",
    "修复：卸载 headless，重装 opencv-python"], BLUE),
    ("坑2", "YOLO 检测静默返回空", [
    "根因：torch 按 numpy 1.x 编译，与 numpy 2.4 不兼容",
    "修复：numpy 降级 1.26.4（opencv 5.0 实测兼容）"], ORANGE),
    ("坑3", "按键抓拍后图传中断", [
    "根因：摄像头独占，二次 VideoCapture 抢占",
    "修复：图传线程持有设备，抓拍改读“最新帧缓存”"], BLUE)]
for i, (tag, head, lines, color) in enumerate(pits):
    y = 1.5 + i * 1.75
    card(s, 0.75, y, 11.8, 1.6, tag, head, lines,
         BLUE if i % 2 == 0 else ORANGE, 14, 16)
txt(s, 0.75, 6.55, 11.8, 0.45,
    "每个坑都定位到根因并写进报告 —— 真实性本身就是答辩的底气",
    15.5, BLUE, True, PP_ALIGN.CENTER)

# ---- 重排页序：20 页最终顺序 ----
# 现有 15 页 idx 0..14，新增 5 页 idx 15..19
order = [0, 1, 2, 3, 15, 4, 5, 6, 7, 16, 8, 9, 10, 17, 11, 12, 13, 18, 19,
         14]
lst = prs.slides._sldIdLst
els = list(lst)
for i in order:
    lst.append(els[i])          # append 已存在元素 = 移动

prs.save(SRC)
print("saved", SRC, "slides:", len(prs.slides._sldIdLst))