import html
import unicodedata

PAGE_SIZE = 18
MAX_TEXT_LENGTH = 80
MAX_PAGES = 10

# Unicode mathematical alphabets for Latin letters and digits.
_MAPS = [
    ("𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙", "𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳", "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"),
    ("𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡", "𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻", "0123456789"),
    ("𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉", "𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣", "0123456789"),
    ("𝕬𝕭𝕮𝕯𝕰𝕱𝕲𝕳𝕴𝕵𝕶𝕷𝕸𝕹𝕺𝕻𝕼𝕽𝕾𝕿𝖀𝖁𝖂𝖃𝖄𝖅", "𝖆𝖇𝖈𝖉𝖊𝖋𝖌𝖍𝖎𝖏𝖐𝖑𝖒𝖓𝖔𝖕𝖖𝖗𝖘𝖙𝖚𝖛𝖜𝖝𝖞𝖟", "0123456789"),
    ("ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ", "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ", "０１２３４５６７８９"),
]

def _convert(text: str, upper: str, lower: str, digits: str) -> str:
    out = []
    for ch in text:
        if "A" <= ch <= "Z":
            out.append(upper[ord(ch) - ord("A")])
        elif "a" <= ch <= "z":
            out.append(lower[ord(ch) - ord("a")])
        elif "0" <= ch <= "9" and len(digits) == 10:
            out.append(digits[ord(ch) - ord("0")])
        else:
            out.append(ch)
    return "".join(out)

def generate_styles(text: str):
    text = unicodedata.normalize("NFC", text)
    styles = []
    names = ["𝗕𝗼𝗹𝗱", "𝘐𝘵𝘢𝘭𝘪𝘤", "𝙼𝚘𝚗𝚘", "𝕲𝖔𝖙𝖍𝖎𝖈", "Ｆｕｌｌｗｉｄｔｈ"]
    for name, mapping in zip(names, _MAPS):
        converted = _convert(text, *mapping)
        if converted != text:
            styles.append((name, converted))
    # Preserve the source's Pashto/Dari/Arabic letters. For such text, styles
    # that only alter Latin letters still retain the original script.
    if not styles:
        styles.append(("اصلي متن", text))
    return styles

def page_text(original: str, styles, page: int):
    total = max(1, (len(styles) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(int(page), total - 1))
    start = page * PAGE_SIZE
    selected = styles[start:start + PAGE_SIZE]
    lines = [f"✨ <b>د متن سټایلونه</b>\n📝 اصلي متن: <code>{html.escape(original)}</code>\n"]
    for i, (name, value) in enumerate(selected, start + 1):
        lines.append(f"{i}. <b>{html.escape(name)}</b>\n<code>{html.escape(value)}</code>")
    lines.append(f"\n📄 پاڼه {page + 1} له {total}")
    return "\n\n".join(lines), total
