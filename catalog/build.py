"""Собирает PDF-каталог 3D-моделей: python3 build.py  (нужны Python 3, Node.js и Playwright с Chromium).

Картинки для моделей ищутся по порядку:
  1. Printables — автоматически через публичный API (картинка и статистика).
  2. images/<ключ>.jpg|jpeg|png|webp — файл, положенный вручную.
  3. image-urls.txt — строка «<ключ> <url картинки>», картинка скачивается.
  4. Thingiverse — через официальный API, если задан THINGIVERSE_TOKEN.
  5. Иначе — плашка с названием площадки. Такие модели перечисляются в NEED-IMAGES.md.
"""
import html, io, json, os, re, subprocess, sys, urllib.request

from PIL import Image

from models import SECTIONS

HERE = os.path.dirname(os.path.abspath(__file__))
MANUAL = os.path.join(HERE, "images")
BUILD = os.path.join(HERE, "build")
IMG = os.path.join(BUILD, "img")
PDF = os.path.join(HERE, "..", "3d-models-catalog.pdf")
UA = {"User-Agent": "Mozilla/5.0"}

Q = 'query { print(id: "%s") { id name slug downloadCount likesCount makesCount image { filePath } user { publicUsername } } }'


def fetch(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=30).read()


def save_image(raw, key):
    """Приводит любую картинку к JPEG до 640x480 на белом фоне."""
    im = Image.open(io.BytesIO(raw)).convert("RGBA")
    im.thumbnail((640, 480))
    bg = Image.new("RGB", im.size, (255, 255, 255))
    bg.paste(im, mask=im.split()[3])
    path = os.path.join(IMG, key + ".jpg")
    bg.save(path, "JPEG", quality=82)
    return path


def key_for(url):
    """Ключ картинки по адресу модели: mw-1742588, mw-collection-26943780, tv-4283898, cults-<slug>."""
    for pattern, prefix in ((r"makerworld\.com/.*/models/(\d+)", "mw-"),
                            (r"makerworld\.com/.*/collections/(\d+)", "mw-collection-"),
                            (r"thingiverse\.com/thing:(\d+)", "tv-"),
                            (r"cults3d\.com/.*/([^/?#]+)$", "cults-")):
        m = re.search(pattern, url)
        if m:
            return prefix + m.group(1)
    raise ValueError("неизвестная площадка: " + url)


def read_image_urls():
    path = os.path.join(HERE, "image-urls.txt")
    if not os.path.exists(path):
        return {}
    pairs = (line.split(None, 1) for line in open(path, encoding="utf-8")
             if line.strip() and not line.startswith("#"))
    return {k: v.strip() for k, v in pairs}


def thingiverse_image(thing_id):
    token = os.environ.get("THINGIVERSE_TOKEN")
    if not token:
        return None
    thing = json.loads(fetch("https://api.thingiverse.com/things/%s" % thing_id,
                             headers={"Authorization": "Bearer " + token}))
    sizes = (thing.get("default_image") or {}).get("sizes") or []
    large = [s["url"] for s in sizes if s.get("type") == "display" and s.get("size") == "large"]
    return (large or [thing.get("thumbnail")])[0]


def external_image(url, image_urls):
    key = key_for(url)
    for ext in ("jpg", "jpeg", "png", "webp"):
        path = os.path.join(MANUAL, "%s.%s" % (key, ext))
        if os.path.exists(path):
            return key, save_image(open(path, "rb").read(), key)
    src = image_urls.get(key)
    if not src and key.startswith("tv-"):
        src = thingiverse_image(key[3:])
    if src:
        try:
            return key, save_image(fetch(src), key)
        except Exception as e:
            print("  не удалось скачать %s: %s" % (src, e), file=sys.stderr)
    return key, None


def printables(pid):
    body = json.dumps({"query": Q % pid}).encode()
    p = json.loads(fetch("https://api.printables.com/graphql/", body, {"content-type": "application/json"}))["data"]["print"]
    img = None
    if p.get("image"):
        fp = p["image"]["filePath"]
        d, f = fp.rsplit("/", 1)
        thumb = "https://media.printables.com/%s/thumbs/inside/640x480/jpg/%s.jpg" % (d, f.rsplit(".", 1)[0])
        for u in (thumb, "https://media.printables.com/" + fp):
            try:
                img = save_image(fetch(u), "printables-" + pid)
                break
            except Exception:
                pass
    return p, img


def card(item, image_urls, missing):
    ref, title, platform, desc = item
    stats = ""
    if ref.isdigit():
        p, img = printables(ref)
        url = "https://www.printables.com/model/%s-%s" % (p["id"], p["slug"])
        title = "%s (%s)" % (p["name"], p["user"]["publicUsername"])
        stats = "⬇ %d &nbsp; ♥ %d &nbsp; 🖨 %d" % (p["downloadCount"], p["likesCount"], p["makesCount"])
    else:
        url = ref
        key, img = external_image(url, image_urls)
        if not img:
            missing.append((key, title, url))
    pic = ('<img src="build/img/%s">' % os.path.basename(img)) if img else \
        '<div class="ph ph-%s"><b>%s</b><span>превью — на странице модели</span></div>' % (platform.lower(), platform)
    return ('<div class="card"><a href="{u}">{pic}</a><div class="body">'
            '<span class="tag tag-{pl}">{p}</span>'
            '<h3><a href="{u}">{t}</a></h3><p>{d}</p>'
            '<div class="stats">{s}</div><a class="url" href="{u}">{ue}</a></div></div>').format(
        u=html.escape(url), pic=pic, pl=platform.lower(), p=platform, t=html.escape(title),
        d=html.escape(desc), s=stats or "статистика — на странице модели", ue=html.escape(url))


def write_missing(missing):
    path = os.path.join(HERE, "NEED-IMAGES.md")
    if not missing:
        if os.path.exists(path):
            os.remove(path)
        return
    lines = ["# Модели без картинки", "",
             "Сохраните картинку как `images/<ключ>.jpg` или добавьте строку `<ключ> <url>` в `image-urls.txt` (см. README.md).", "",
             "| Ключ | Модель |", "|---|---|"]
    lines += ["| `%s` | [%s](%s) |" % m for m in missing]
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def main():
    os.makedirs(IMG, exist_ok=True)
    image_urls = read_image_urls()
    missing = []
    parts = []
    for name, note, items in SECTIONS:
        parts.append('<section><h2>%s</h2>%s<div class="grid">%s</div></section>' % (
            html.escape(name), ('<p class="note">%s</p>' % html.escape(note)) if note else "",
            "".join(card(i, image_urls, missing) for i in items)))
        print("готово:", name, file=sys.stderr)
    tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    page = os.path.join(BUILD, "..", "catalog.html")
    open(page, "w", encoding="utf-8").write(tpl.replace("{{SECTIONS}}", "".join(parts)))
    write_missing(missing)
    subprocess.run(["node", os.path.join(HERE, "render.js"), os.path.abspath(page), os.path.abspath(PDF)], check=True)
    print("PDF: %s, без картинки: %d" % (os.path.abspath(PDF), len(missing)), file=sys.stderr)


if __name__ == "__main__":
    main()
