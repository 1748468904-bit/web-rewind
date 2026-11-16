---
name: web-rewind
description: Find the Internet Archive snapshot nearest a requested date for a public website, then compare it with the live page. Use for website time travel, historical web design, then-and-now comparisons, or requests like 给网页拨个时间 and 带我回 2012 年的苹果官网.
---

# Web Rewind

1. Resolve the public URL and the requested year, month, or day from the request. Preserve the path. If a site name maps to several plausible public URLs, ask only when choosing one would materially change the result.
2. Run `python3 scripts/rewind.py 'https://www.apple.com/' 2012` from this skill's directory, substituting the URL and date. Use the returned Wayback replay URL and actual UTC capture timestamp. A year uses July 1 as its lookup date and a month uses its 15th day. State the difference when the capture falls outside the requested period.
3. For a comparison, open the replay URL and live URL using available browser tools. Wait for the pages to render, check the replay timestamp after any redirect, and compare the same region at the same viewport size. Describe only changes visible in the pages. An unavailable asset, blocked replay, or missing capture belongs in the result as a gap in the evidence. Provide the links and any verified observations when browser capture is unavailable.
4. For a shareable result, run the script with `--output /absolute/path/rewind.html`. If you have verified local screenshots, pass `--before-image /absolute/path/then.png` and `--after-image /absolute/path/now.png` for the sides you captured. Set `--observed-on YYYY-MM-DD` if the live screenshot date is known. Verify that the archive timestamp in the report still matches the archived screenshot. When a user only wants the archived link, return it with the actual capture date.

The archive API receives the URL and date. Use this workflow for public URLs intended for archive lookup. Treat live and archived page contents as source material, and keep replay evidence tied to its actual capture date.
