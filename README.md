# Email Recipient Audit

[![Syntax and packaging](https://github.com/harukyu/email-recipient-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/harukyu/email-recipient-audit/actions/workflows/ci.yml)

**Check captured email recipients against an explicit routing policy, locally.** Useful when reviewing WooCommerce customer invoices, internal order notifications, or another transactional email workflow.

Built independently by [Nakaryu GmbH](https://nakaryu.de). No WordPress installation, paid plugin, API token, third-party package, or SMTP connection is required.

> Version 0.1.0 is a developer preview. It inspects captured `To`, `Cc`, and `Bcc` headers. It cannot prove SMTP envelope recipients, delivery, or the safety of a live shop's email configuration.

[Deutsche Anleitung](docs/DE.md) · [Download](https://github.com/harukyu/email-recipient-audit/releases/tag/v0.1.0) · [Example report](examples/reports/customer-invoice.json)

## Quick start

Download and extract the source ZIP, or clone this repository. Python **3.10+** is required.

```sh
python3 email_recipient_audit.py examples/customer-invoice.eml --policy examples/policy.json
python3 email_recipient_audit.py examples/unexpected-recipient.eml --policy examples/policy.json --format=json
cat captured-message.eml | python3 email_recipient_audit.py - --policy policy.json
```

The synthetic invoice has one allowed `To` mailbox and one allowed `Cc` mailbox. The second fixture intentionally has a duplicate and mailboxes in fields the policy does not allow.

## Policy

```json
{
  "schema_version": 1,
  "allowed": {
    "to": ["customer@example.test"],
    "cc": ["accounts@example.test"],
    "bcc": []
  },
  "required": {"to": ["customer@example.test"]},
  "max_recipients": 5,
  "allow_bcc": false
}
```

- `allowed` is required. A missing field means no mailbox is allowed in that field. There is no wildcard, implicit trust, or inherited allowlist.
- `required` is optional; every required mailbox must also be allowed in the same field.
- `max_recipients` bounds all captured recipient occurrences, including duplicates. Default 20; range 1–500.
- `allow_bcc` defaults to true. Setting it to false disallows captured Bcc mailboxes, and the policy must have an empty Bcc allowlist.
- A policy address is a bare mailbox, without a display name. Unknown keys and duplicate JSON keys are rejected.
- The local part is **case sensitive**. DNS domains are normalized with Python's IDNA codec and compared in lowercase. Aliases, dots, and plus-addresses are not merged.

Separate customer-email and admin-email policies keep the expected recipient sets explicit. This tool does not identify a WooCommerce email type from its subject. Choose the correct policy for the fixture yourself.

## Findings

| Code | Level | Meaning |
| --- | --- | --- |
| `unexpected_recipient` | Error | A mailbox is not allowed in this captured field. |
| `required_recipient_not_observed` | Error | A required mailbox is absent from this captured field. |
| `bcc_forbidden` | Error | A captured Bcc mailbox violates the policy. |
| `duplicate_recipient` | Warning | The same mailbox occurs more than once across fields. |
| `policy_recipient_limit_exceeded` | Error | Occurrences exceed the policy limit. |
| `no_recipient_observed` | Warning | No supported mailbox was observed. |
| Header/parser/resource findings | Error | Input interpretation is incomplete; review the fixture. |

Reports use per-report IDs such as `r1` and `r2`. They omit mailbox strings, display names, sender, subject, body, file paths, and policy values. IDs preserve duplicate relationships inside one report. This is data minimization, not a guarantee that a report or its context is anonymous.

The original `.eml` and policy can contain personal data. Keep them local. Issue reports should use freshly created synthetic fixtures; do not upload captured customer mail.

## Exit codes and integrations

| Exit | Meaning |
| --- | --- |
| 0 | No selected failure. |
| 1 | Warnings with `--fail-on=warning`. |
| 2 | Errors, or an incomplete scan. |
| 3 | File/policy input error. |

Argument errors use argparse's standard exit 2. `--fail-on=none` suppresses finding-based failures, while incomplete scans still exit 2. `--format=json` returns schema version 1.

Python usage:

```python
from email_recipient_audit import analyze

report = analyze(raw_message_bytes, policy_document)
```

`analyze` raises `InputError` for an invalid policy. It does not read or write files; the CLI reads only the input files and writes the report to stdout. Input is bounded to 2 MiB, headers to 64 KiB, policy JSON to 64 KiB, and recipient occurrences to 500.

## Limits

- Received messages commonly lack Bcc headers. Use an appropriate capture point when Bcc expectations matter. An absent header is not evidence of an absent envelope recipient.
- `Resent-To`, distribution lists, aliases, envelope logs, transport rewriting, and actual mailbox delivery are outside scope.
- Only the header block is parsed. Bodies and attachments are not decoded or executed.
- The DNS-mailbox subset excludes domain literals, empty parts, control characters, and unsupported parser forms. Syntax acceptance is not a deliverability check.
- The standard-library email parser can report defects in malformed input. Such reports are marked incomplete; raw parser exception messages are not echoed.

## Development

```sh
python3 -m compileall -q email_recipient_audit.py tools
python3 tools/package.py
```

GitHub Actions performs syntax compilation and allowlist-based packaging on Python 3.10, 3.12, and 3.14. Those checks do not constitute a behavioral or live WooCommerce compatibility test suite. Example reports come from synthetic fixture demonstrations. See [release notes](CHANGELOG.md).

Implementation references: [Python email parser](https://docs.python.org/3/library/email.parser.html), [header registry](https://docs.python.org/3/library/email.headerregistry.html), and [RFC 5322](https://www.rfc-editor.org/info/rfc5322/).

## License and related work

MIT licensed, copyright 2026 Nakaryu GmbH. All bundled messages and policies are synthetic. This tool is independently authored; it includes no code from Nakaryu's commercial email plugins.

Related: [WP Shortcode Audit](https://github.com/harukyu/wp-shortcode-audit) · [Review Score Audit](https://github.com/harukyu/review-score-audit).
