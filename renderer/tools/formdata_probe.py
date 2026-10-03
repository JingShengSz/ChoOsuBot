"""What Content-Type does aiohttp.FormData produce for a text-only form?

The plugin builds the render request with `aiohttp.FormData`. If that comes out as
`application/x-www-form-urlencoded`, the server's multipart-only parser sees no fields at
all — which is exactly the 400 the live run produced.
"""
import asyncio

import aiohttp


async def describe(label: str, form: aiohttp.FormData) -> None:
    body = form()
    print(f"{label}:")
    print("  is_multipart :", form.is_multipart)
    print("  content_type :", form.headers.get("Content-Type"))
    print("  body preview :", body.decode("utf-8", "replace")[:200].replace("\r\n", "\\r\\n"))
    print()


async def main() -> None:
    # exactly how the plugin builds it
    form = aiohttp.FormData()
    form.add_field("bid", "2467450")
    form.add_field("skin", "boj 1-10K")
    form.add_field("scroll", "30")
    await describe("text-only FormData", form)

    form2 = aiohttp.FormData()
    form2.add_field("bid", "2467450")
    form2.add_field("osr", b"\x00\x01", filename="replay.osr",
                    content_type="application/octet-stream")
    await describe("with a file field", form2)


asyncio.run(main())
