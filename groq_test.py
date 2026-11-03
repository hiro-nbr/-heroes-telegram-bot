# -*- coding: utf-8 -*-
"""تست مستقیم اتصال به Groq API با کلید داخل bot.py."""
import asyncio
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

from groq import AsyncGroq

src = open("bot.py", encoding="utf-8").read()
key = re.search(r'GROQ_API_KEY\s*=\s*"([^"]*)"', src).group(1)
model = re.search(r'GROQ_MODEL\s*=\s*"([^"]*)"', src).group(1)

out = open("groq_result.txt", "w", encoding="utf-8")


async def main():
    out.write(f"model: {model}\n")
    try:
        client = AsyncGroq(api_key=key, timeout=30)
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "خودت را در یک جمله فارسی معرفی کن."}],
            max_tokens=300,
        )
        answer = resp.choices[0].message.content
        out.write(f"RESULT: {'OK ✅' if answer and answer.strip() else 'EMPTY ❌'} — جواب مدل: {(answer or '')!r}\n")
    except Exception as e:
        out.write(f"RESULT: FAILED ❌\n{type(e).__name__}: {e}\n")
    finally:
        out.close()
        print("done")


asyncio.run(main())
