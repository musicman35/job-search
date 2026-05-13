"""Email summary: build HTML + send via SMTP.

Top-picks threshold (per spec):
  - category=ic with fit_score >= 7, OR
  - category=rotational with fit_score >= 6 AND track in TECHNICAL_TRACKS
"""

import html
import os
import smtplib
from email.message import EmailMessage

from config import TECHNICAL_TRACKS


def _to_int(value) -> int:
    try:
        return int(str(value).strip())
    except (ValueError, TypeError, AttributeError):
        return 0


def is_top_pick(row: dict) -> bool:
    score = _to_int(row.get("fit_score"))
    cat = (row.get("category") or "").strip()
    if cat == "ic":
        return score >= 7
    if cat == "rotational":
        return score >= 6 and (row.get("track") or "").strip() in TECHNICAL_TRACKS
    return False


def _h(s) -> str:
    return html.escape("" if s is None else str(s))


def _render_top_pick(row: dict) -> str:
    title = _h(row.get("title"))
    company = _h(row.get("company"))
    tier = _h(row.get("tier"))
    cat = (row.get("category") or "").strip()
    track = (row.get("track") or "").strip()
    badge = f"{cat}" + (f" · {_h(track)}" if cat == "rotational" and track else "")
    location = _h(row.get("location"))
    url = _h(row.get("url"))
    score = _h(row.get("fit_score"))
    reasoning = _h(row.get("fit_reasoning") or "")
    return (
        '<div style="margin: 0 0 18px; padding: 0;">'
        f'<div><strong style="font-size:1.05em;">{title}</strong> '
        f'<span style="color:#444;">— {company}</span> '
        f'<span style="color:#888; font-size:0.9em;">(T{tier} · {badge} · {location} · fit {score}/10)</span>'
        "</div>"
        f'<div style="color:#555; font-size:0.92em; margin: 2px 0 4px;">{reasoning}</div>'
        f'<div style="font-size:0.85em;"><a href="{url}" style="color:#1a73e8;">{url}</a></div>'
        "</div>"
    )


def _render_other_new(row: dict) -> str:
    title = _h(row.get("title"))
    company = _h(row.get("company"))
    cat = (row.get("category") or "").strip()
    track = (row.get("track") or "").strip()
    badge = cat + (f"/{_h(track)}" if cat == "rotational" and track else "")
    url = _h(row.get("url"))
    score = _h(row.get("fit_score"))
    return (
        f'<li><strong>{title}</strong> — {company} '
        f'<span style="color:#888;">({badge}, fit {score}/10)</span> '
        f'· <a href="{url}" style="color:#1a73e8;">link</a></li>'
    )


def _render_closed(row: dict) -> str:
    return f'<li>{_h(row.get("title"))} — {_h(row.get("company"))}</li>'


def _render_stats(run_stats: dict) -> str:
    succeeded = run_stats.get("succeeded") or []
    failed = run_stats.get("failed") or []  # list of (company, error_msg)
    parts = [f'<p><strong>Fetched:</strong> {len(succeeded)} source(s) succeeded']
    if succeeded:
        parts.append(
            f' <span style="color:#888;">({_h(", ".join(succeeded))})</span>'
        )
    parts.append("</p>")
    if failed:
        parts.append('<p><strong style="color:#b00;">Errors:</strong></p><ul>')
        for name, err in failed:
            parts.append(f"<li>{_h(name)}: {_h(err)}</li>")
        parts.append("</ul>")
    return "".join(parts)


def build_email(
    new_rows: list[dict],
    closed_rows: list[dict],
    run_stats: dict,
    today: str,
) -> tuple[str, str] | None:
    """Returns (subject, html_body) or None if nothing to report."""
    if not new_rows and not closed_rows:
        return None

    subject = f"Job tracker: {len(new_rows)} new, {len(closed_rows)} closed ({today})"

    top_picks = sorted(
        (r for r in new_rows if is_top_pick(r)),
        key=lambda r: _to_int(r.get("fit_score")),
        reverse=True,
    )
    other_new = [r for r in new_rows if not is_top_pick(r)]

    sections: list[str] = []

    sections.append(
        f'<h2 style="margin: 18px 0 8px; font-size: 1.15em;">Top picks ({len(top_picks)})</h2>'
    )
    if top_picks:
        sections.extend(_render_top_pick(r) for r in top_picks)
    else:
        sections.append('<p style="color:#888;">No new postings cleared the top-picks threshold.</p>')

    if other_new:
        sections.append(
            f'<h2 style="margin: 24px 0 8px; font-size: 1.15em;">Other new postings ({len(other_new)})</h2>'
        )
        sections.append("<ul>")
        sections.extend(_render_other_new(r) for r in other_new)
        sections.append("</ul>")

    if closed_rows:
        sections.append(
            f'<h2 style="margin: 24px 0 8px; font-size: 1.15em;">Closed ({len(closed_rows)})</h2>'
        )
        sections.append("<ul>")
        sections.extend(_render_closed(r) for r in closed_rows)
        sections.append("</ul>")

    sections.append(
        '<h2 style="margin: 24px 0 8px; font-size: 1.15em;">Run stats</h2>'
    )
    sections.append(_render_stats(run_stats))

    body = (
        '<html><body style="font-family: -apple-system, BlinkMacSystemFont, '
        '\'Segoe UI\', Helvetica, Arial, sans-serif; '
        'color:#222; max-width: 760px; margin: 0; padding: 8px 4px;">'
        + "".join(sections)
        + "</body></html>"
    )
    return subject, body


def send_email(subject: str, html_body: str) -> None:
    host = os.environ["SMTP_HOST"]
    port = int(os.environ["SMTP_PORT"])
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    sender = os.environ["EMAIL_FROM"]
    recipient = os.environ["EMAIL_TO"]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content("This email requires an HTML-capable client.")
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)
