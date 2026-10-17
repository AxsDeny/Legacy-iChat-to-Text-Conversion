#!/usr/bin/env python3
"""
ichat2txt.py - convert old iChat .ichat transcripts (Mac OS X 10.5-10.7 era)
into plain, readable .txt files and preserve image and pdf attachments when possible.

Usage:
    python3 ichat2txt.py FILE_OR_FOLDER [FILE_OR_FOLDER ...] [-o OUTPUT_FOLDER]

  * Give it single .ichat files or whole folders (searched recursively).
  * By default each .txt is written next to its .ichat file.
    With -o, all .txt files go into OUTPUT_FOLDER instead (keeping subfolders).
  * Pictures sent inside a chat are saved to a "<name> attachments" folder
    next to the .txt, and the transcript notes where each one went.
  * Times are shown in this computer's local time zone.
  * Add --utc to show times in UTC instead.

"""

import argparse
import datetime as dt
import os
import plistlib
import sys

APPLE_EPOCH = dt.datetime(2001, 1, 1, tzinfo=dt.timezone.utc)


class Unarchiver:
    """Minimal NSKeyedArchiver decoder for the object types iChat uses."""

    def __init__(self, data):
        self.objects = data["$objects"]
        self.top = data["$top"]
        self.cache = {}

    def get(self, ref):
        if isinstance(ref, plistlib.UID):
            idx = ref.data
            if idx in self.cache:
                return self.cache[idx]
            self.cache[idx] = None  # guards against reference cycles
            val = self.decode(self.objects[idx])
            self.cache[idx] = val
            return val
        return self.decode(ref)

    def classname(self, obj):
        if isinstance(obj, dict) and "$class" in obj:
            return self.objects[obj["$class"].data].get("$classname", "")
        return ""

    def decode(self, obj):
        if obj == "$null":
            return None
        if isinstance(obj, plistlib.UID):
            return self.get(obj)
        if isinstance(obj, list):
            return [self.get(o) for o in obj]
        if not isinstance(obj, dict):
            return obj

        cls = self.classname(obj)
        if "NS.objects" in obj and "NS.keys" in obj:  # dictionary
            keys = [self.get(k) for k in obj["NS.keys"]]
            vals = [self.get(v) for v in obj["NS.objects"]]
            return dict(zip(keys, vals))
        if "NS.objects" in obj:  # array / set
            return [self.get(o) for o in obj["NS.objects"]]
        if "NS.string" in obj:  # NSString / NSMutableString
            return obj["NS.string"]
        if "NS.time" in obj:  # NSDate
            return APPLE_EPOCH + dt.timedelta(seconds=obj["NS.time"])
        if "NSString" in obj and "Attributed" in cls:  # NSAttributedString
            return self.get(obj["NSString"])
        if "NS.relative" in obj:  # NSURL
            return self.get(obj["NS.relative"])

        # Any other object (InstantMessage, Presentity, ...): decode fields.
        out = {"_class": cls}
        for k, v in obj.items():
            if k != "$class":
               out[k] = v if isinstance(v, (int, float, bool, bytes)) else self.get(v)
        return out


def sender_name(sender):
    if not isinstance(sender, dict):
        return None
    return sender.get("ID") or sender.get("ServiceLoginID")


# Signatures used to pull a picture back out of iChat's embedded file blob.
FILE_SIGNATURES = [
    (b"\xff\xd8\xff", b"\xff\xd9", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", b"IEND\xaeB`\x82", ".png"),
    (b"GIF87a", b"\x00;", ".gif"),
    (b"GIF89a", b"\x00;", ".gif"),
    (b"%PDF", b"%%EOF", ".pdf"),
    (b"II*\x00", None, ".tiff"),
    (b"MM\x00*", None, ".tiff"),
]


def find_attachments(u, ref, seen=None):
    """Walk the raw archive under one message and collect embedded files.

    Returns a list of (suggested_name_or_None, bytes)."""
    if seen is None:
        seen = set()
    found, names = [], []

    def walk(r):
        if isinstance(r, plistlib.UID):
            if r.data in seen:
                return
            seen.add(r.data)
            r = u.objects[r.data]
        if isinstance(r, dict):
            if "NSFileWrapperData" in r:
                blob = u.objects[r["NSFileWrapperData"].data]
                if isinstance(blob, dict):
                    blob = blob.get("NS.data")
                if isinstance(blob, bytes):
                    found.append(blob)
            for k, v in r.items():
                if k != "$class":
                    walk(v)
        elif isinstance(r, list):
            for v in r:
                walk(v)
        elif isinstance(r, str) and "/" in r and os.path.splitext(r)[1]:
            names.append(os.path.basename(r))  # e.g. FezInlineFilePath

    walk(ref)
    out = []
    for i, blob in enumerate(found):
        name = names[i] if i < len(names) else None
        out.append((name, extract_file(blob)))
    return out


def extract_file(blob):
    """Pull the real file out of a serialized NSFileWrapper blob."""
    if not blob.startswith(b"rtfd"):
        return blob, None
    for start_sig, end_sig, ext in FILE_SIGNATURES:
        start = blob.find(start_sig)
        if start == -1:
            continue
        if end_sig:
            end = blob.rfind(end_sig)
            if end > start:
                return blob[start:end + len(end_sig)], ext
        return blob[start:], ext
    return None, None


def message_text(msg, attach_labels=()):
    text = msg.get("MessageText")
    if not isinstance(text, str) or not text:
        text = msg.get("OriginalMessage")
    if not isinstance(text, str):
        text = ""
    # Status lines like "%@ is now online." name the person in "Subject"
    subject = sender_name(msg.get("Subject"))
    if "%@" in text:
        text = text.replace("%@", subject or "Buddy")
    # U+FFFC marks an inline image or file that was sent
    labels = list(attach_labels)
    while "￼" in text:
        label = labels.pop(0) if labels else "[attachment]"
        text = text.replace("￼", label, 1)
    for label in labels:  # attachments with no placeholder in the text
        text = (text + " " + label).strip()
    files = msg.get("FileTransferGUIDs")
    if files and "[" not in text:
        text = (text + " [file transfer - file not stored in log]").strip()
    return text


def fmt_time(t, use_utc):
    if not isinstance(t, dt.datetime):
        return "??:??:??"
    t = t if use_utc else t.astimezone()
    return t


def convert(path, out_path, use_utc=False):
    with open(path, "rb") as f:
        data = plistlib.load(f)
    if data.get("$archiver") != "NSKeyedArchiver":
        raise ValueError("not an NSKeyedArchiver file (maybe a pre-2007 .chat log?)")

    u = Unarchiver(data)
    root = u.get(u.top["root"])
    meta = u.get(u.top["metadata"]) if "metadata" in u.top else {}
    meta = meta if isinstance(meta, dict) else {}

    # Root is an array; the message list is the element holding InstantMessages.
    messages, raw_refs = [], []
    raw_root = u.objects[u.top["root"].data].get("NS.objects", [])
    for idx, item in enumerate(root if isinstance(root, list) else []):
        if isinstance(item, list) and any(
            isinstance(m, dict) and "InstantMessage" in m.get("_class", "") for m in item
        ):
            raw_list = u.objects[raw_root[idx].data].get("NS.objects", [])
            pairs = [(m, r) for m, r in zip(item, raw_list) if isinstance(m, dict)]
            messages = [m for m, _ in pairs]
            raw_refs = [r for _, r in pairs]
            break

    # Embedded pictures/files get saved to "<transcript name> attachments/"
    attach_dir = os.path.splitext(out_path)[0] + " attachments"
    saved_count = 0

    lines = []
    service = meta.get("Service") or (root[0] if root and isinstance(root[0], str) else "")
    ids = meta.get("PresentityIDs") or []
    names = meta.get("Participants") or []
    people = []
    for i, pid in enumerate(ids):
        name = names[i] if i < len(names) else None
        people.append(f"{pid} ({name})" if name and name != pid else str(pid))

    start, end = meta.get("StartTime"), meta.get("EndTime")
    lines.append(f"iChat transcript: {os.path.basename(path)}")
    if service:
        lines.append(f"Service: {service}")
    if meta.get("ChatRoom"):
        lines.append(f"Chat room: {meta['ChatRoom']}")
    if people:
        lines.append("Participants: " + ", ".join(people))
    if isinstance(start, dt.datetime):
        s = fmt_time(start, use_utc)
        line = "Started: " + s.strftime("%A, %B %d, %Y at %I:%M:%S %p %Z").replace(" 0", " ")
        lines.append(line)
    if isinstance(end, dt.datetime):
        e = fmt_time(end, use_utc)
        lines.append("Ended:   " + e.strftime("%A, %B %d, %Y at %I:%M:%S %p %Z").replace(" 0", " "))
    lines.append("=" * 60)

    width = max([len(sender_name(m.get("Sender")) or "") for m in messages] + [1])
    last_day = None
    for m, raw in zip(messages, raw_refs):
        labels = []
        for name, (data, ext) in find_attachments(u, raw.data and u.objects[raw.data].get("MessageText")):
            if data is None:
                labels.append(f"[attachment: {name or 'unknown'} - could not extract]")
                continue
            saved_count += 1
            fname = name or f"attachment {saved_count}{ext or '.bin'}"
            os.makedirs(attach_dir, exist_ok=True)
            dest = os.path.join(attach_dir, fname)
            base_, ext_ = os.path.splitext(dest)
            n = 2
            while os.path.exists(dest):
                dest = f"{base_} ({n}){ext_}"
                n += 1
            with open(dest, "wb") as f:
                f.write(data)
            rel = os.path.relpath(dest, os.path.dirname(out_path) or ".")
            labels.append(f"[picture/file saved as: {rel}]")

        t = fmt_time(m.get("Time"), use_utc)
        if isinstance(t, dt.datetime):
            day = t.date()
            if day != last_day:
                if last_day is not None:
                    lines.append("")
                lines.append(f"--- {t.strftime('%A, %B')} {t.day}, {t.year} ---")
                last_day = day
            stamp = t.strftime("%I:%M:%S %p")
        else:
            stamp = "??:??:?? ??"

        who = sender_name(m.get("Sender"))
        text = message_text(m, labels)
        if who:
            body = text.replace("\n", "\n" + " " * (len(stamp) + width + 4))
            lines.append(f"[{stamp}] {who.rjust(width)}: {body}")
        else:  # status / system message (e.g. "X went away")
            lines.append(f"[{stamp}] * {text}")

    if not messages:
        lines.append("(no messages)")
    return "\n".join(lines) + "\n"


def find_files(inputs):
    for p in inputs:
        if os.path.isdir(p):
            for dirpath, _, files in os.walk(p):
                for name in sorted(files):
                    if name.lower().endswith(".ichat"):
                        yield os.path.join(dirpath, name), p
        else:
            yield p, os.path.dirname(p) or "."


def main():
    ap = argparse.ArgumentParser(description="Convert iChat .ichat files to text.")
    ap.add_argument("inputs", nargs="+", help=".ichat files or folders")
    ap.add_argument("-o", "--output", help="folder to write .txt files into")
    ap.add_argument("--utc", action="store_true", help="show times in UTC")
    args = ap.parse_args()

    ok = bad = 0
    for path, base in find_files(args.inputs):
        stem =os.path.splitext(path)[0] + ".txt"
        if args.output:
            rel = os.path.relpath(stem, base)
            out = os.path.join(args.output, rel)
            os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        else:
            out = stem
        try:
            text = convert(path, out, args.utc)
        except Exception as e:
            print(f"SKIPPED {path}: {e}", file=sys.stderr)
            bad += 1
            continue
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {out}")
        ok += 1
    print(f"\nDone: {ok} converted, {bad} skipped.")


if __name__ == "__main__":
    main()
