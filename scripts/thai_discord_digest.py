# -*- coding: utf-8 -*-
"""Thai Discord digest — post-process daily reports into a Thai, Discord-friendly
message with a TL;DR summary at the end, then push to a Discord webhook.

Discord does not render markdown tables, so the LLM is instructed to reformat
everything into emoji-led lines instead. Runs as a separate workflow step after
the main analysis so the built-in (English) Discord push can stay disabled.

Env:
    OPENAI_API_KEY            required
    DISCORD_WEBHOOK_URL_TH    required (webhook that receives the Thai digest)
    DIGEST_MODEL              optional, default: gpt-5.5
    REPORTS_DIR               optional, default: reports
"""

from __future__ import annotations

import glob
import json
import os
import sys
import time
import urllib.error
import urllib.request

DISCORD_CHAR_LIMIT = 1900   # keep headroom under Discord's hard 2000 limit
MAX_REPORT_CHARS = 120000   # full dashboard report for 9 stocks is ~124k chars
RETRY_WAITS = (30, 60, 90)  # backoff seconds between 429 retries

SYSTEM_PROMPT = """คุณคือผู้ช่วยสรุปรายงานวิเคราะห์หุ้นรายวันสำหรับนักเทรดชาวไทยชื่อ Beef

หน้าที่: แปลงรายงานภาษาอังกฤษ/จีนที่ได้รับ ให้เป็นข้อความ Discord ภาษาไทยที่อ่านง่ายและลงมือทำได้จริง

กติกาเรื่องความถูกต้อง (สำคัญที่สุด):
- ตัวเลขทุกตัว (แนวรับ แนวต้าน ราคา MA คะแนน) ต้องมาจากรายงานต้นทางเท่านั้น — ห้ามแต่งตัวเลขเองเด็ดขาด
- ถ้ารายงานไม่มีตัวเลขแนวรับ/แนวต้านของหุ้นตัวไหน ให้เขียนว่า "ไม่มีข้อมูล" แทน

กติกาการจัดรูปแบบ:
1. ภาษาไทยทั้งหมด — ยกเว้น ticker (เช่น NVDA), ตัวเลข, และศัพท์เทคนิคที่แปลแล้วงง (คงอังกฤษ + วงเล็บอธิบายไทยสั้นๆ ครั้งแรก)
2. ห้ามใช้ตาราง markdown เด็ดขาด (Discord แสดงผลไม่ได้) — ใช้บรรทัด + emoji แทน
3. โครงสร้าง:

   **📊 รายงานหุ้นประจำวัน [วันที่]**

   **🌎 ภาพรวมตลาด US** — 2-4 บรรทัด (ดัชนีหลัก + โทนตลาด)

   **หุ้นรายตัว** — เรียงคะแนนมาก→น้อย รูปแบบต่อตัว (กระชับ ตัวละ ~4 บรรทัด):
   [emoji] **TICKER** — คะแนน XX/100 · [คำแนะนำไทย] · เทรนด์[ไทยสั้น]
   ├ 🛡️ แนวรับ: XXX.X · 🚧 แนวต้าน: XXX.X
   ├ สัญญาณ: MA [เรียงตัว/หลุด], วอลุ่ม [สถานะ], ข่าว/sentiment [สั้น]
   └ ทำไง: [action 1 บรรทัด เช่น "หลุด 194 = ออก, ยืนเหนือ MA10 + วอลุ่มมา = ถือต่อ"]

   emoji: 🟢 ซื้อ/ถือ (≥60) · ⚪ เฝ้าดู (40-59) · 🟠 ลดพอร์ต (25-39) · 🔴 ขาย (<25)

4. จบด้วย 2 ส่วนนี้เสมอ (บังคับ):

   **📌 สรุปท้าย (ไม่มีเวลา อ่านตรงนี้พอ)**
   • โทนตลาดวันนี้: 1 บรรทัด
   • หุ้นที่ต้องจัดการด่วน: ระบุ ticker + ระดับราคาที่ต้องดู
   • หุ้นที่ปล่อยได้: 1 บรรทัด

   **🎯 Action Plan — เลือกเอา A / B / C**
   วิเคราะห์จากสัญญาณหลายตัวประกอบ (เทรนด์ MA + แนวรับแนวต้าน + วอลุ่ม + sentiment + ข่าว) แล้วเสนอ 3 ทาง:
   **A) เซฟไว้ก่อน (ลดความเสี่ยง)** — ทำอะไรบ้าง ระบุ ticker + จำนวน (เช่น ลดครึ่ง) + ราคา trigger ชัดๆ
   **B) ตามระบบ (สมดุล)** — ถือตามสัญญาณ ตั้ง stop ตรงไหน รอ confirm อะไร
   **C) เชิงรุก (รับความเสี่ยงได้)** — ถ้าจะเสี่ยงเพิ่ม ต้องเห็นสัญญาณอะไรก่อน + จุดเข้า/จุดตัดขาดทุน
   ปิดท้าย 1 บรรทัด: "วันนี้แนะนำ: [A/B/C] เพราะ [เหตุผลสั้น]"

5. ความยาวรวมไม่เกิน ~5500 ตัวอักษร
6. คำแนะนำแปลงไทย: Buy=ซื้อ, Hold=ถือ, Watch=เฝ้าดู, Reduce=ลดพอร์ต, Sell=ขาย"""


def latest(pattern: str) -> str | None:
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def read_reports(reports_dir: str) -> str:
    # per-part caps so the (large) stock report can't crowd out the market review
    parts: list[str] = []
    for name, pattern, cap in (
        ("MARKET REVIEW", os.path.join(reports_dir, "market_review_*.md"), 4000),
        ("STOCK REPORT", os.path.join(reports_dir, "report_*.md"), MAX_REPORT_CHARS - 4000),
    ):
        path = latest(pattern)
        if path:
            with open(path, "r", encoding="utf-8") as f:
                body = f.read()[:cap]
            parts.append(f"===== {name} ({os.path.basename(path)}) =====\n{body}")
    return "\n\n".join(parts)


def _chat_once(api_key: str, model: str, report_text: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"รายงานวันนี้:\n\n{report_text}"},
        ],
        # gpt-5.x models reject non-default temperature -> omit it
        "max_completion_tokens": 10000,  # Thai output is token-heavy; detailed plan needs room
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"]
    if not content or not content.strip():
        raise RuntimeError(f"empty LLM response: {json.dumps(data)[:500]}")
    return content.strip()


def call_openai(api_key: str, model: str, report_text: str) -> str:
    """Call the model with 429 backoff; fall back to gpt-5.4-mini as a last resort."""
    fallback_model = "gpt-5.4-mini"
    for attempt, wait in enumerate((0,) + RETRY_WAITS):
        if wait:
            print(f"rate limited (429), retry in {wait}s...")
            time.sleep(wait)
        try:
            return _chat_once(api_key, model, report_text)
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
    if model != fallback_model:
        print(f"still rate limited, falling back to {fallback_model}")
        time.sleep(30)
        return _chat_once(api_key, fallback_model, report_text)
    raise RuntimeError("rate limited on all attempts")


def split_chunks(text: str, limit: int = DISCORD_CHAR_LIMIT) -> list[str]:
    """Split on newline boundaries so each chunk stays under Discord's limit."""
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        # a single overlong line gets hard-split
        while len(line) > limit:
            head, line = line[:limit], line[limit:]
            if current:
                chunks.append(current)
                current = ""
            chunks.append(head)
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current.strip():
        chunks.append(current)
    return chunks


def post_discord(webhook_url: str, text: str) -> None:
    chunks = split_chunks(text)
    for i, chunk in enumerate(chunks, 1):
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps({"content": chunk}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                # Discord/Cloudflare rejects the default Python-urllib UA with 403
                "User-Agent": "daily-stock-analysis-thai-digest/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status not in (200, 204):
                raise RuntimeError(f"discord chunk {i}/{len(chunks)} failed: HTTP {resp.status}")
        print(f"discord chunk {i}/{len(chunks)} sent")
        if i < len(chunks):
            time.sleep(1)  # stay clear of webhook rate limits


def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    webhook = os.environ.get("DISCORD_WEBHOOK_URL_TH", "").strip()
    model = os.environ.get("DIGEST_MODEL", "gpt-5.5").strip()
    reports_dir = os.environ.get("REPORTS_DIR", "reports").strip()

    if not api_key or not webhook:
        print("ERROR: OPENAI_API_KEY and DISCORD_WEBHOOK_URL_TH are required", file=sys.stderr)
        return 1

    report_text = read_reports(reports_dir)
    if not report_text.strip():
        print(f"ERROR: no reports found under {reports_dir}/", file=sys.stderr)
        return 1

    print(f"input: {len(report_text)} chars, model: {model}")
    digest = call_openai(api_key, model, report_text)
    print(f"digest: {len(digest)} chars")
    post_discord(webhook, digest)
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
