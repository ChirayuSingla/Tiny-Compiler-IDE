"""Draw the compiler pipeline / architecture figure used in the report (needs Pillow)."""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "docs", "img", "architecture.png")


def font(size, bold=False):
    names = ["arialbd.ttf" if bold else "arial.ttf", "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"]
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


def box(d, xy, title, sub, fill):
    x0, y0, x1, y1 = xy
    d.rounded_rectangle(xy, radius=14, fill=fill, outline=(40, 60, 90), width=3)
    f1, f2 = font(26, True), font(19)
    tw = d.textlength(title, font=f1)
    d.text(((x0 + x1 - tw) / 2, y0 + 18), title, fill=(15, 25, 45), font=f1)
    for i, line in enumerate(sub.split("\n")):
        w = d.textlength(line, font=f2)
        d.text(((x0 + x1 - w) / 2, y0 + 60 + i * 26), line, fill=(40, 50, 70), font=f2)


def arrow(d, p0, p1, label=None):
    d.line([p0, p1], fill=(40, 60, 90), width=4)
    x, y = p1
    px, py = p0
    if abs(x - px) >= abs(y - py):
        s = 1 if x > px else -1
        d.polygon([(x, y), (x - s * 16, y - 9), (x - s * 16, y + 9)], fill=(40, 60, 90))
    else:
        s = 1 if y > py else -1
        d.polygon([(x, y), (x - 9, y - s * 16), (x + 9, y - s * 16)], fill=(40, 60, 90))
    if label:
        f = font(17)
        w = d.textlength(label, font=f)
        d.text(((p0[0] + p1[0]) / 2 - w / 2, (p0[1] + p1[1]) / 2 - 30), label,
               fill=(90, 40, 40), font=f)


def main():
    W, H = 2000, 970
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.text((40, 20), "Tiny Compiler - processing pipeline and modules", fill=(15, 25, 45),
           font=font(34, True))
    blue, green, orange, grey = (205, 225, 250), (210, 240, 215), (252, 232, 200), (232, 232, 238)
    bw, bh, y1 = 380, 150, 110
    xs = [40, 560, 1080, 1600]
    box(d, (xs[0], y1, xs[0] + bw, y1 + bh), "Source", "program.tiny\n(text)", grey)
    box(d, (xs[1], y1, xs[1] + bw, y1 + bh), "1. Lexer", "lexer.py\ncharacters -> tokens", blue)
    box(d, (xs[2], y1, xs[2] + bw, y1 + bh), "2. Parser", "parser.py + ast_nodes.py\ntokens -> AST", blue)
    box(d, (xs[3], y1, xs[3] + bw, y1 + bh), "3. Semantic analysis",
        "semantic.py + symbol_table.py\nscopes, types, checks", blue)
    for i in range(3):
        arrow(d, (xs[i] + bw, y1 + bh // 2), (xs[i + 1], y1 + bh // 2),
              ["characters", "tokens", "AST"][i])
    y2 = 470
    box(d, (xs[3], y2, xs[3] + bw, y2 + bh), "4. IR generator", "ir.py\nannotated AST -> TAC", green)
    box(d, (xs[2], y2, xs[2] + bw, y2 + bh), "5. Code generator", "codegen.py\nTAC -> stack code", green)
    box(d, (xs[1], y2, xs[1] + bw, y2 + bh), "6. Stack VM", "vm.py (+ runtime.py)\nexecutes stack code", orange)
    box(d, (xs[0], y2, xs[0] + bw, y2 + bh), "Output", "program output\n(stdout)", grey)
    arrow(d, (xs[3] + bw // 2, y1 + bh), (xs[3] + bw // 2, y2), "annotated AST")
    arrow(d, (xs[3], y2 + bh // 2), (xs[2] + bw, y2 + bh // 2), "TAC")
    arrow(d, (xs[2], y2 + bh // 2), (xs[1] + bw, y2 + bh // 2), "stack code")
    arrow(d, (xs[1], y2 + bh // 2), (xs[0] + bw, y2 + bh // 2), "runs")
    # side modules
    box(d, (40, 740, 1000, 890), "Diagnostics (diagnostics.py)",
        "lexical / syntax / semantic / runtime errors, line:column + source caret\n"
        "the pipeline stops after the first phase that reports errors", (250, 220, 220))
    box(d, (1040, 740, 1980, 890), "CLI (cli.py, main.py) and API (pipeline.py)",
        "--tokens --ast --symbols --ir --code --all --check --input --trace", grey)
    d.text((40, 915), "ir.py also contains a TAC interpreter: tests run every example on both the TAC "
           "interpreter and the stack VM and compare the output.", fill=(40, 50, 70), font=font(20))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img.save(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    sys.exit(main())
