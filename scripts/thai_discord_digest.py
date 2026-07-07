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
import urllib.request

DISCORD_CHAR_LIMIT = 1900  # keep headroom under Discord's hard 2000 limit
MAX_REPORT_CHARS = 60000   # truncate huge inputs before sending to the LLM

SYSTEM_PROMPT = """คุณคือผู้ช่วยสรุปรายงานวิเคราะห์หุ้นรายวันสำหรับนักเทรดชาวไทยชื่อ Beef

หน้าที่: แปลงรายงานภาษาอังกฤษ/จีนที่ได้รับ ให้เป็นข้อความ Discord ภาษาไทยที่อ่านง่าย

กติกาการจัดรูปแบบ (สำคัญมาก):
1. ภาษาไทยทั้งหมด — ยกเว้น ticker (เช่น NVDA), ตัวเลข, และศัพท์เทคนิคที่แปลแล้วงง (ให้คงอังกฤษ + วงเล็บอธิบายไทยสั้นๆ ครั้งแรกที่ใช้)
2. ห้ามใช้ตาราง markdown เด็ดขาด (Discord แสดงผลไม่ได้) — ใช้บรรทัด + emoji แทน
3. โครงสร้าง:
   **📊 รายงานหุ้นประจำวัน [วันที่]**

   **🌎 ภาพรวมตลาด US** — 2-4 บรรทัด

   **หุ้นรายตัว** — เรียงจากคะแนนมาก→น้อย รูปแบบต่อตัว:
   [emoji สัญญาณ] **TICKER** — คะแนน XX/100 · [คำแนะนำไทย]
   └ เหตุผลสั้น 1 บรรทัด

   emoji สัญญาณ: 🟢 ซื้อ/ถือ (คะแนน≥60) · ⚪ เฝ้าดู (40-59) · 🟠 ลดพอร์ต (25-39) · 🔴 ขาย (<25)
4. จบด้วยส่วนสรุป (บังคับ):
   **📌 สรุปท้าย (ไม่มีเวลาอ่านทั้งหมด อ่านตรงนี้พอ)**
   • ต้องทำอะไรวันนี้: 1-3 bullet ชัดๆ (ตัวไหนต้องระวัง/ลด/ขาย)
   • โทนตลาดวันนี้: 1 บรรทัด
5. ความยาวรวมไม่เกิน ~3500 ตัวอักษร — กระชับ ตัดน้ำ
6. คำแนะนำแปลงเป็นไทย: Buy=ซื้อ, Hold=ถือ, Watch=เฝ้าดู, Reduce=ลดพอร์ต, Sell=ขาย"""


def latest(pattern: str) -> str | None:
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def read_reports(reports_dir: str) -> str:
    parts: list[str] = []
    for name, pattern in (
        ("MARKET REVIEW", os.path.join(reports_dir, "market_review_*.md")),
        ("STOCK REPORT", os.path.join(reports_dir, "report_*.md")),
    ):
        path = latest(pattern)
        if path:
            with open(path, "r", encoding="utf-8") as f:
                parts.append(f"===== {name} ({os.path.basename(path)}) =====\n{f.read()}")
    combined = "\n\n".join(parts)
    return combined[:MAX_REPORT_CHARS]


def call_openai(api_key: str, model: str, report_text: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"รายงานวันนี้:\n\n{report_text}"},
        ],
        # gpt-5.x models reject non-default temperature -> omit it
        "max_completion_tokens": 4096,
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
