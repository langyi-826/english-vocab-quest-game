# -*- coding: utf-8 -*-
"""
把家长提供的词表 JSON 注入闯关游戏模板，生成一个可直接双击打开的单文件 HTML。

用法：
    python build_game.py --in 词表.json --out "小宇的单词闯关.html"
    python build_game.py --in 词表.json --out out.html --template 自定义模板.html

词表 JSON 格式（最简）：
{
  "title": "小宇的单词闯关",
  "books": [
    {
      "key": "7a", "name": "七年级上册", "short": "七上",
      "stage": "j", "grade": "7", "review": false,
      "words": [
        {"e": "nice", "c": "令人愉快的；友好的", "u": "U1", "p": "adj.", "t": "单词"},
        {"e": "look after", "c": "照顾", "u": "U1", "t": "短语"}
      ]
    }
  ]
}

说明：
- stage：p=小学，j=初中；grade：3-9
- review=true 的册子不用给 words，脚本会自动把同年级各正课册的词汇总（由短到长重排）
- 每个正课册每 10 词一关，复习册每 12 词一关
- 单词按提供的顺序切关；同一册内请按课本单元顺序排列
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TPL = HERE.parent / "assets" / "game_template.html"

LEVEL_SIZE = 10
REVIEW_SIZE = 12


def norm_words(book):
    """清洗一册的词：去空、去重（同册内大小写不敏感）、统一字段。"""
    seen = set()
    out = []
    for w in book.get("words") or []:
        if isinstance(w, str):
            w = {"e": w}
        en = str(w.get("e", "")).strip()
        cn = str(w.get("c", "")).strip()
        if not en or not cn:
            continue
        key = en.lower().replace(" ", "")
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "e": en,
            "c": cn,
            "q": str(w.get("q") or cn).strip(),
            "p": str(w.get("p") or "").strip(),
            "u": str(w.get("u") or "").strip(),
            "t": str(w.get("t") or ("短语" if " " in en else "单词")),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True, help="词表 JSON 路径")
    ap.add_argument("--out", dest="dst", required=True, help="输出 HTML 路径")
    ap.add_argument("--template", dest="tpl", default=str(DEFAULT_TPL), help="模板路径")
    args = ap.parse_args()

    src = Path(args.src)
    tpl_path = Path(args.tpl)
    if not src.exists():
        sys.exit(f"找不到词表文件：{src}")
    if not tpl_path.exists():
        sys.exit(f"找不到模板文件：{tpl_path}")

    data = json.loads(src.read_text(encoding="utf-8"))
    books_in = data.get("books") or []
    if not books_in:
        sys.exit("词表里没有 books，至少给一册")

    books = []
    book_words = []          # 与 books 同序，正课册的词
    for i, b in enumerate(books_in):
        stage = str(b.get("stage") or "j")
        grade = str(b.get("grade") or ("3" if stage == "p" else "7"))
        books.append({
            "key": str(b.get("key") or f"b{i}"),
            "name": str(b.get("name") or f"第{i+1}册"),
            "short": str(b.get("short") or b.get("name") or f"册{i+1}"),
            "stage": stage,
            "grade": grade,
            "review": bool(b.get("review")),
        })
        book_words.append([] if b.get("review") else norm_words(b))

    # 复习册：同年级同阶段各正课册汇总，按词长由短到长重排（短词先上，循序渐进）
    for i, bk in enumerate(books):
        if not bk["review"]:
            continue
        pool = []
        for j, b2 in enumerate(books):
            if b2["review"]:
                continue
            if b2["stage"] == bk["stage"] and b2["grade"] == bk["grade"]:
                pool.extend(book_words[j])
        pool.sort(key=lambda w: (len(re.sub(r"[^A-Za-z]", "", w["e"])), w["e"].lower()))
        book_words[i] = pool

    words, wid = [], 0
    empty_books = []
    for bi, wl in enumerate(book_words):
        if not wl:
            empty_books.append(books[bi]["name"])
            continue
        for w in wl:
            wid += 1
            words.append({
                "i": wid, "e": w["e"], "p": w["p"], "c": w["c"], "q": w["q"],
                "b": bi, "u": w["u"], "t": w["t"],
            })

    if not words:
        sys.exit("清洗后一个词都没有，检查词表格式")

    tpl = tpl_path.read_text(encoding="utf-8")
    for mark in ("__WORDS__", "__BOOKS__", "__REVIEW_SIZE__"):
        if mark not in tpl:
            sys.exit(f"模板缺少占位符 {mark}，可能不是正确的游戏模板")

    out = tpl.replace("__WORDS__", json.dumps(words, ensure_ascii=False, separators=(",", ":")))
    out = out.replace("__BOOKS__", json.dumps(books, ensure_ascii=False, separators=(",", ":")))
    out = out.replace("__REVIEW_SIZE__", str(REVIEW_SIZE))

    # 标题与教材版本名：家长给什么写什么，没给就不显示，绝不错标成别的版本
    title = str(data.get("title") or "英语背单词闯关游戏").strip()
    title_html = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    edition = data.get("edition") or {}
    ed_p = str(edition.get("p") or "").replace("'", "\\'").strip()
    ed_j = str(edition.get("j") or "").replace("'", "\\'").strip()
    for mark, val in (("__TITLE__", title_html), ("__EDITION_P__", ed_p), ("__EDITION_J__", ed_j)):
        if mark in out:
            out = out.replace(mark, val)
    # 无内置发音包 / 无字典扩展：模板会自动退回浏览器朗读、隐藏练习句
    for mark, val in (("__AMAP__", "{}"), ("__AUDIO__", "[]"), ("__DICT__", "{}")):
        if mark in tpl:
            out = out.replace(mark, val)

    dst = Path(args.dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(out, encoding="utf-8")

    # 统计
    n_level = 0
    for bi, bk in enumerate(books):
        if bk["review"]:
            continue
        cnt = sum(1 for w in words if w["b"] == bi)
        n_level += -(-cnt // LEVEL_SIZE)
    for bi, bk in enumerate(books):
        if not bk["review"]:
            continue
        cnt = sum(1 for w in words if w["b"] == bi)
        n_level += -(-cnt // REVIEW_SIZE) if cnt else 0

    print(f"词条 {len(words)} · 册数 {len(books)} · 关卡 {n_level}")
    print(f"输出 {dst}（{dst.stat().st_size/1024/1024:.1f} MB）")
    if empty_books:
        print("提示：这些册子没有词，已跳过：" + "、".join(empty_books))


if __name__ == "__main__":
    main()
