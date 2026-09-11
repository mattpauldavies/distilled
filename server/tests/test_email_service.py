"""Rendering safety for transactional emails.

Workspace names are attacker-controlled free text (any signed-up user owns a
workspace they can rename), so everything interpolated into email HTML must be
escaped — otherwise invites become a phishing vector sent from our domain.
"""

from app.services.email_service import (
    _render_invitation_html,
    _render_invitation_text,
    _subject_text,
)

HOSTILE_TENANT = '</h1><a href="https://evil.example/reset">Reset now</a><div style="display:none">'
HOSTILE_INVITER = "<script>alert(1)</script>"


def test_invitation_html_escapes_tenant_and_inviter_names():
    html_out = _render_invitation_html(
        tenant_name=HOSTILE_TENANT,
        inviter_name=HOSTILE_INVITER,
        accept_url="https://app.example.com/invitations/accept?token=tok",
    )
    assert "<script>" not in html_out
    assert '<a href="https://evil.example/reset">' not in html_out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_out
    # The legitimate accept link must survive untouched.
    assert '<a href="https://app.example.com/invitations/accept?token=tok"' in html_out


def test_invitation_html_leaves_plain_names_readable():
    html_out = _render_invitation_html(
        tenant_name="Acme & Co",
        inviter_name="mattd",
        accept_url="https://app.example.com/accept",
    )
    assert "Acme &amp; Co" in html_out
    assert "mattd invited you" in html_out


def test_subject_strips_control_characters():
    subject = _subject_text(tenant_name="Acme\r\nBcc: victim", inviter_name="matt\nd")
    assert "\r" not in subject
    assert "\n" not in subject
    assert "matt d invited you to Acme Bcc: victim on Distilled" == subject


def test_invitation_text_part_is_plain():
    text = _render_invitation_text(
        tenant_name=HOSTILE_TENANT,
        inviter_name="mattd",
        accept_url="https://app.example.com/accept",
    )
    # Plain-text part is inert; it must simply contain the accept URL.
    assert "https://app.example.com/accept" in text
