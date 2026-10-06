"""Offline checks of captured email recipient headers. Never sends mail."""

from __future__ import annotations

import argparse
from collections import Counter
from email import policy as email_policy
from email.headerregistry import Address
from email.errors import MessageError
from email.parser import BytesHeaderParser
import json
from pathlib import Path
import re
import sys

VERSION = "0.1.0"
MAX_BYTES = 2 * 1024 * 1024
MAX_HEADER_BYTES = 64 * 1024
MAX_RECIPIENTS = 500
FIELDS = ("to", "cc", "bcc")


class InputError(ValueError):
    """Invalid input; messages intentionally omit original input values."""


def canonical_address(username: str, domain: str) -> str:
    """Preserve the local part; compare DNS domains in canonical IDNA form."""
    if not username or not domain or any(ord(c) < 32 or ord(c) == 127 for c in username + domain):
        raise InputError("A mailbox has an empty part or a control character.")
    if len(username) > 64 or len(domain) > 253 or len(username + domain) > 320:
        raise InputError("A mailbox exceeds the supported length limits.")
    if domain.startswith("["):
        raise InputError("Domain-literal mailboxes are outside the supported subset.")
    try:
        normalized_domain = domain.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise InputError("A mailbox domain cannot be normalized.") from exc
    labels = normalized_domain.split(".")
    if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels):
        raise InputError("A mailbox does not use a supported DNS domain.")
    # A tuple-like serialized key avoids ambiguity for quoted local parts.
    return json.dumps([username, normalized_domain], ensure_ascii=True, separators=(",", ":"))


def policy_address(value: object) -> str:
    if not isinstance(value, str) or len(value) > 320 or "\n" in value or "\r" in value:
        raise InputError("Policy addresses must be bounded mailbox strings.")
    try:
        address = Address(addr_spec=value)
        return canonical_address(address.username, address.domain)
    except (ValueError, IndexError, MessageError) as exc:
        raise InputError("A policy address is not a supported mailbox.") from exc


def address_sets(value: object, label: str) -> dict[str, set[str]]:
    if not isinstance(value, dict) or set(value) - set(FIELDS):
        raise InputError(f"{label} must contain only to, cc, and bcc arrays.")
    result = {}
    for field in FIELDS:
        items = value.get(field, [])
        if not isinstance(items, list) or len(items) > MAX_RECIPIENTS:
            raise InputError(f"Each {label} field must be an array of at most 500 mailboxes.")
        keys = [policy_address(item) for item in items]
        if len(keys) != len(set(keys)):
            raise InputError(f"A {label} field contains duplicate mailboxes.")
        result[field] = set(keys)
    return result


def validate_policy(document: object) -> dict:
    allowed_keys = {"schema_version", "allowed", "required", "max_recipients", "allow_bcc"}
    if not isinstance(document, dict) or set(document) - allowed_keys:
        raise InputError("Policy must be an object using only documented keys.")
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        raise InputError("Policy schema_version must be integer 1.")
    if "allowed" not in document:
        raise InputError("Policy needs explicit allowed recipient arrays.")
    allowed = address_sets(document["allowed"], "allowed")
    required = address_sets(document.get("required", {}), "required")
    limit = document.get("max_recipients", 20)
    allow_bcc = document.get("allow_bcc", True)
    if type(limit) is not int or not 1 <= limit <= MAX_RECIPIENTS or type(allow_bcc) is not bool:
        raise InputError("max_recipients must be 1–500; allow_bcc must be a boolean.")
    for field in FIELDS:
        if not required[field] <= allowed[field]:
            raise InputError("Every required recipient must be allowed in the same field.")
    if not allow_bcc and (allowed["bcc"] or required["bcc"]):
        raise InputError("A policy forbidding Bcc cannot allow or require Bcc recipients.")
    return {"allowed": allowed, "required": required, "max_recipients": limit, "allow_bcc": allow_bcc}


def analyze(raw_message: bytes, policy_document: object) -> dict:
    rules = validate_policy(policy_document)
    report = {
        "schema_version": 1, "analyzer_version": VERSION, "complete": True,
        "scope": "captured_to_cc_bcc_headers_only", "identities": "per_report_ordinal_ids",
        "summary": {"recipient_occurrences": 0, "unique_recipients": 0, "errors": 0, "warnings": 0},
        "recipients": [], "issues": [],
        "limitations": [
            "Headers do not prove SMTP envelope recipients or delivery.",
            "Bcc may be removed before a received message is captured.",
            "Local parts are case sensitive; aliases and plus-addresses are not merged.",
        ],
    }

    def issue(code: str, severity: str, message: str, field: str = "", recipient: str = "") -> None:
        report["issues"].append({"code": code, "severity": severity, "message": message,
                                 "field": field, "recipient_id": recipient})
        report["summary"]["errors" if severity == "error" else "warnings"] += 1

    if len(raw_message) > MAX_BYTES:
        report["complete"] = False
        issue("input_limit_exceeded", "error", "Message exceeds 2 MiB; capture a smaller fixture.")
        return report
    boundary = re.search(rb"\r?\n\r?\n", raw_message)
    header = raw_message[:boundary.start()] if boundary else raw_message
    if len(header) > MAX_HEADER_BYTES:
        report["complete"] = False
        issue("header_limit_exceeded", "error", "Header block exceeds 64 KiB.")
        return report
    if not boundary:
        report["complete"] = False
        issue("missing_header_boundary", "error", "No blank line separates headers and body.")
    try:
        message = BytesHeaderParser(policy=email_policy.default).parsebytes(header + b"\r\n\r\n")
    except (ValueError, IndexError, RecursionError, MessageError):
        report["complete"] = False
        issue("header_parse_failed", "error", "Header parsing failed; raw input is omitted.")
        return report
    if message.defects:
        report["complete"] = False
        issue("malformed_headers", "error", "The parser reported defects in the header block.")
    occurrences: list[tuple[str, str]] = []
    limit_reached = False
    for field in FIELDS:
        if limit_reached:
            break
        try:
            headers = message.get_all(field, [])
            if len(headers) > 1:
                report["complete"] = False
                issue("repeated_recipient_header", "error", "Recipient field occurs more than once.", field)
            for parsed in headers:
                if parsed.defects:
                    report["complete"] = False
                    issue("malformed_recipient_header", "error", "Recipient header has parsing defects.", field)
                for address in parsed.addresses:
                    try:
                        key = canonical_address(address.username, address.domain)
                    except InputError:
                        report["complete"] = False
                        issue("unsupported_mailbox", "error", "A mailbox is outside the supported subset.", field)
                        continue
                    if len(occurrences) >= MAX_RECIPIENTS:
                        report["complete"] = False
                        issue("recipient_limit_exceeded", "error", "More than 500 recipient occurrences.", field)
                        limit_reached = True
                        break
                    occurrences.append((field, key))
                if limit_reached:
                    break
        except (ValueError, IndexError, RecursionError, MessageError):
            report["complete"] = False
            issue("recipient_parse_failed", "error", "Recipient parsing failed; raw input is omitted.", field)
    ids: dict[str, str] = {}
    observed = {field: set() for field in FIELDS}
    for field, key in occurrences:
        identifier = ids.setdefault(key, f"r{len(ids) + 1}")
        observed[field].add(key)
        accepted = key in rules["allowed"][field]
        report["recipients"].append({"id": identifier, "field": field, "allowed": accepted})
        if not accepted:
            issue("unexpected_recipient", "error", "Mailbox is not allowed in this field.", field, identifier)
        if field == "bcc" and not rules["allow_bcc"]:
            issue("bcc_forbidden", "error", "Policy forbids a captured Bcc recipient.", field, identifier)
    for key, count in Counter(key for _, key in occurrences).items():
        if count > 1:
            issue("duplicate_recipient", "warning", "Mailbox occurs more than once across recipient fields.", recipient=ids[key])
    for field in FIELDS:
        missing = len(rules["required"][field] - observed[field])
        if missing:
            issue("required_recipient_not_observed", "error", f"{missing} required mailbox(es) not observed in this captured field.", field)
    if len(occurrences) > rules["max_recipients"]:
        issue("policy_recipient_limit_exceeded", "error", "Recipient occurrences exceed the policy limit.")
    if not occurrences:
        issue("no_recipient_observed", "warning", "No supported recipient mailbox observed in the headers.")
    report["summary"].update(recipient_occurrences=len(occurrences), unique_recipients=len(ids))
    return report


def read_bounded(path: str, maximum: int) -> bytes:
    if path == "-":
        return sys.stdin.buffer.read(maximum + 1)
    with Path(path).open("rb") as stream:
        return stream.read(maximum + 1)


def load_json(raw: bytes) -> object:
    def pairs(items: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise InputError("JSON contains a repeated object key.")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise InputError("Policy is not valid JSON with unique object keys.") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message", help="Captured .eml file, or - for stdin")
    parser.add_argument("--policy", required=True, help="Explicit recipient policy JSON")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--fail-on", choices=("error", "warning", "none"), default="error")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args(argv)
    try:
        if args.policy == "-":
            raise InputError("Policy must be a file; stdin is reserved for the message.")
        raw_policy = read_bounded(args.policy, MAX_HEADER_BYTES)
        if len(raw_policy) > MAX_HEADER_BYTES:
            raise InputError("Policy exceeds 64 KiB.")
        report = analyze(read_bounded(args.message, MAX_BYTES), load_json(raw_policy))
    except (OSError, InputError):
        print("Input error: cannot read input or policy is invalid. No input values are printed.", file=sys.stderr)
        return 3
    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=True))
    else:
        s = report["summary"]
        print(f"Recipient Audit {VERSION}: {s['recipient_occurrences']} occurrences, {s['unique_recipients']} mailboxes")
        print(f"Complete: {report['complete']}; errors: {s['errors']}; warnings: {s['warnings']}")
        for finding in report["issues"]:
            print(f"{finding['severity'].upper()} {finding['code']} {finding['field']} {finding['recipient_id']}: {finding['message']}")
        print("Scope: captured headers only; SMTP envelope and delivery are unverified.")
    if not report["complete"]:
        return 2
    if args.fail_on != "none" and report["summary"]["errors"]:
        return 2
    return 1 if args.fail_on == "warning" and report["summary"]["warnings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
