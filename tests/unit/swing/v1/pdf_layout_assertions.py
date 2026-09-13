"""Read PDF drawing operators, not extractor cursor guesses or OCR."""
from reportlab.pdfbase.pdfmetrics import stringWidth


def text_bounds(page):
    ctm = [1, 0, 0, 1, 0, 0]
    tm = [1, 0, 0, 1, 0, 0]
    stack = []
    leading = 0
    size = 12
    font = "Helvetica"
    result = []
    fonts = page["/Resources"].get("/Font", {})
    for args, op in page.get_contents().operations:
        if op == b"q":
            stack.append(list(ctm))
        elif op == b"Q":
            ctm = stack.pop()
        elif op == b"cm":
            a,b,c,d,e,f = map(float, args)
            A,B,C,D,E,F = ctm
            ctm = [a*A+b*C, a*B+b*D, c*A+d*C, c*B+d*D, e*A+f*C+E, e*B+f*D+F]
        elif op == b"BT":
            tm = [1, 0, 0, 1, 0, 0]
        elif op == b"Tm":
            tm = list(map(float, args))
        elif op == b"Tf":
            font = str(fonts[args[0]]["/BaseFont"]).lstrip("/")
            size = float(args[1])
        elif op == b"TL":
            leading = float(args[0])
        elif op == b"T*":
            tm[5] -= leading
        elif op == b"Td":
            tm[4] += float(args[0]); tm[5] += float(args[1])
        elif op == b"Tj":
            text = str(args[0])
            if text.strip():
                width = stringWidth(text, font, size)
                x = ctm[0]*tm[4] + ctm[2]*tm[5] + ctm[4]
                y = ctm[1]*tm[4] + ctm[3]*tm[5] + ctm[5]
                result.append((text, x, y, x+width*ctm[0], size))
    return result
