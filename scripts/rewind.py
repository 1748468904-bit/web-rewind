#!/usr/bin/env python3
"""Find a Wayback capture and optionally export a self-contained comparison."""

import argparse
import base64
from datetime import date, datetime
from html import escape
import ipaddress
import json
from pathlib import Path
import re
from string import Template
import sys
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


AVAILABILITY_API = "https://archive.org/wayback/available"
TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "report.html"


def public_url(value):
    value = value.strip()
    if not value or any(char.isspace() or ord(char) < 32 for char in value) or "\\" in value:
        raise ValueError("Enter a public web URL without spaces.")
    if value.startswith("//"):
        value = "https:" + value
    elif "://" not in value:
        value = "https://" + value
    parsed = urlsplit(value)
    host = (parsed.hostname or "").rstrip(".")
    if parsed.scheme not in {"http", "https"} or not host or parsed.username is not None:
        raise ValueError("Enter a public HTTP or HTTPS URL without credentials.")
    if parsed.port == 0:
        raise ValueError("Enter a valid URL port.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or host.endswith((".localhost", ".local", ".internal", ".lan", ".home.arpa")):
            raise ValueError("Enter a publicly accessible hostname.") from None
    else:
        if not address.is_global or address.is_multicast:
            raise ValueError("Enter a publicly accessible IP address.")
    return parsed._replace(fragment="").geturl()


def anchor_date(value):
    if not re.fullmatch(r"[0-9]{4}(?:-[0-9]{2}(?:-[0-9]{2})?)?", value):
        raise ValueError("Use YYYY, YYYY-MM, or YYYY-MM-DD.")
    if len(value) == 4:
        value += "-07-01"
    elif len(value) == 7:
        value += "-15"
    return date.fromisoformat(value)


def find_capture(url, anchor):
    query = urlencode({"url": url, "timestamp": anchor.isoformat().replace("-", "")})
    request = Request(f"{AVAILABILITY_API}?{query}", headers={"Accept": "application/json"})
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)

    snapshots = payload.get("archived_snapshots") if isinstance(payload, dict) else None
    if not isinstance(snapshots, dict):
        raise ValueError("Wayback returned an unexpected response.")
    closest = snapshots.get("closest")
    if closest is None:
        return None
    if not isinstance(closest, dict) or not isinstance(closest.get("available"), bool):
        raise ValueError("Wayback returned incomplete capture metadata.")
    if not closest["available"]:
        return None

    timestamp = closest.get("timestamp")
    replay_url = closest.get("url")
    if not isinstance(timestamp, str) or not re.fullmatch(r"[0-9]{14}", timestamp):
        raise ValueError("Wayback returned an invalid capture timestamp.")
    if not isinstance(replay_url, str):
        raise ValueError("Wayback returned an invalid replay link.")
    replay = urlsplit(replay_url)
    if (
        replay.scheme not in {"https", "http"}
        or replay.netloc.lower() != "web.archive.org"
        or not replay.path.startswith(f"/web/{timestamp}/")
    ):
        raise ValueError("Wayback returned an unexpected replay link.")
    captured_at = datetime.strptime(timestamp, "%Y%m%d%H%M%S")
    return {
        "url": replay._replace(scheme="https").geturl(),
        "captured_at_utc": captured_at.isoformat() + "Z",
        "http_status": closest.get("status"),
    }


def image_markup(path, alt, link):
    if path is None:
        return f'<div class="page-placeholder"><a href="{escape(link)}" rel="noreferrer" target="_blank">Open page ↗</a></div>'
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        media_type = "png"
    elif data.startswith(b"\xff\xd8\xff"):
        media_type = "jpeg"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        media_type = "webp"
    else:
        raise ValueError(f"{path} must be a PNG, JPEG, or WebP image.")
    encoded = base64.b64encode(data).decode("ascii")
    return f'<img src="data:image/{media_type};base64,{encoded}" alt="{escape(alt)}">'


def write_report(output, result, before_image, after_image):
    live_url = result["url"]
    archive_url = result["archive"]["url"]
    capture_date = result["archive"]["captured_at_utc"][:10]
    observed_on = result.get("live_observed_on")
    current_heading = f'<time datetime="{observed_on}">{observed_on}</time>' if observed_on else "Live page"
    period_alert = ""
    if not result["capture_in_requested_period"]:
        period_alert = '<p class="notice">The closest capture is outside the requested period.</p>'
    template = Template(TEMPLATE.read_text(encoding="utf-8"))
    report = template.substitute(
        host=escape(urlsplit(live_url).netloc),
        request_period=escape(result["requested_period"]),
        anchor_date=escape(result["lookup_date_utc"]),
        capture_date=escape(capture_date),
        current_heading=current_heading,
        period_alert=period_alert,
        before_url=escape(archive_url),
        after_url=escape(live_url),
        before_preview=image_markup(before_image, f"Archived page from {capture_date}", archive_url),
        after_preview=image_markup(after_image, "Screenshot of the live page", live_url),
    )
    output.write_text(report, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Public website URL")
    parser.add_argument("period", help="Requested date in YYYY, YYYY-MM, or YYYY-MM-DD format")
    parser.add_argument("--output", type=Path, help="Write a standalone HTML comparison")
    parser.add_argument("--before-image", type=Path, help="Verified screenshot of the Wayback capture")
    parser.add_argument("--after-image", type=Path, help="Verified screenshot of the live page")
    parser.add_argument("--observed-on", type=date.fromisoformat, help="Date of the live screenshot (YYYY-MM-DD)")
    args = parser.parse_args()
    if args.output is None and (args.before_image or args.after_image):
        parser.error("screenshot options require --output")
    if args.observed_on and args.after_image is None:
        parser.error("--observed-on requires --after-image")

    try:
        url = public_url(args.url)
        anchor = anchor_date(args.period)
        capture = find_capture(url, anchor)
        result = {
            "url": url,
            "requested_period": args.period,
            "lookup_date_utc": anchor.isoformat(),
            "archive": capture,
        }
        if capture is None:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            print("Wayback did not return an available capture for this URL.", file=sys.stderr)
            return 1
        result["capture_in_requested_period"] = capture["captured_at_utc"].startswith(args.period)
        if args.observed_on:
            result["live_observed_on"] = args.observed_on.isoformat()
        if args.output:
            write_report(args.output, result, args.before_image, args.after_image)
            result["report"] = str(args.output.resolve())
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except URLError as exc:
        print(f"Wayback lookup failed: {exc}", file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        print(f"Web Rewind: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
