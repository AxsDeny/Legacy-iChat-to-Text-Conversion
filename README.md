# ichat2txt

Convert old Apple iChat transcripts (`.ichat` files) into plain text you can read in any text editor.

iChat saved conversations in a binary format (an `NSKeyedArchiver` property list) that modern versions of macOS can no longer open, since Messages replaced iChat. If you have a folder of old `.ichat` logs, this script turns each one into a readable `.txt` file, and saves any pictures that were sent in the chat.

## Example output

```
iChat transcript: buddy123_on_2010-05-06_at_10.30.ichat
Service: AIM
Participants: myhandle (Jane Doe), buddy123
Started: Thursday, May 6, 2010 at 10:30:05 AM EDT
Ended:   Thursday, May 6, 2010 at 11:02:02 AM EDT
============================================================
--- Thursday, May 6, 2010 ---
[10:30:05 AM]  buddy123: hi
[10:30:09 AM]  myhandle: hey! lunch today?
[10:30:21 AM]  buddy123: sure, noon?
[10:31:12 AM]  myhandle: [picture/file saved as: buddy123_on_2010-05-06_at_10.30 attachments/iChat Image(2312885101).jpeg]
[10:54:49 AM] * buddy123 has gone offline.
```

## Requirements

- Python 3.8 or newer
- Nothing else. The script only uses Python's standard library.

On a Mac, run `python3 --version` in Terminal to check. If Python isn't installed, macOS will offer to install Apple's command line tools, which include it. The script also works on Windows and Linux.

## Usage

Download `ichat2txt.py`, then run it from a terminal and give it a single `.ichat` file or a whole folder (it also looks inside subfolders):

```sh
python3 ichat2txt.py ~/Documents/iChats
```

iChat kept its logs in `~/Documents/iChats` by default, organized into dated subfolders.

### Options

| Option | What it does |
| --- | --- |
| `-o FOLDER`, `--output FOLDER` | Write the `.txt` files into `FOLDER` instead of next to each `.ichat` file. The original subfolder structure is kept. |
| `--utc` | Show times in UTC instead of your computer's local time zone. |
| `-h`, `--help` | Show help. |

### Examples

Convert one file. The `.txt` is written next to it:

```sh
python3 ichat2txt.py "buddy123_on_2010-05-06_at_10.30.ichat"
```

Convert everything into a separate folder and leave the originals untouched:

```sh
python3 ichat2txt.py ~/Documents/iChats -o ~/Desktop/chats_txt
```

Convert several folders at once:

```sh
python3 ichat2txt.py ~/Documents/iChats "/Volumes/Backup/Old iChats" -o ~/Desktop/chats_txt
```

## What gets converted

- **Messages** from every participant, with a timestamp. Messages with several lines stay indented under the sender's name.
- **Header** with the service (AIM, Jabber, etc.), participants and their display names, and the start and end times.
- **Date headings** whenever a conversation runs past midnight.
- **Status events** such as "went offline" or "Direct Instant Message session started", marked with `*`.
- **Pictures pasted into a chat.** They're saved into a `<transcript name> attachments` folder next to the `.txt` file, and the transcript shows where each one went.
- **Links**, which come through as plain URLs.

## Limitations

- **Files sent with iChat's file transfer** were never stored in the log. The transcript notes `[file transfer - file not stored in log]` where one was sent.
- **Pre-2007 `.chat` files** from iChat 1–3 (Mac OS X 10.2–10.4) use an older format and are not supported. Those files are reported as `SKIPPED` and the script carries on with the rest.
- **Text formatting** such as fonts, colors and bold is dropped. The output is plain text.
- **Times** are shown in the time zone your computer is set to now, not necessarily the one you were in when you chatted. Use `--utc` if you want a fixed reference.

## Troubleshooting

- **`SKIPPED ...: not an NSKeyedArchiver file`**: the file is probably an older `.chat` log or isn't an iChat file.
- **`python3: command not found`**: install Python 3 from [python.org](https://www.python.org/downloads/), or on a Mac run `xcode-select --install`.
- **A transcript looks wrong**: please open an issue. Attach the `.ichat` file if you're comfortable sharing it, or describe what's missing.

## Privacy

Everything runs locally on your computer. The script reads your chat logs and writes text files, and never sends anything over the network.

## License

MIT
