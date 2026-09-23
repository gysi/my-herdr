"""A one-line text prompt for popups, where Esc cancels.

herdr's own prompts cancel on Esc, and a popup receives Esc like any other key,
so a popup that ignored it would feel broken. `input()` cannot see it: the
terminal's line editor just prints `^[`. So the terminal goes into cbreak mode
for the duration of the prompt and the line is edited here: printable text,
Backspace, Ctrl-U to clear, Enter to accept, Esc, Ctrl-C or Ctrl-D to cancel.

Arrow and function keys also start with Esc, so an Esc followed immediately by
more bytes is an escape sequence and is swallowed, not taken as a cancel. A
human pressing Esc is never followed by another byte within the same instant.
"""
import codecs
import os
import select
import sys

ESC = b"\x1b"
CANCEL = (b"\x03", b"\x04")      # Ctrl-C, Ctrl-D
ACCEPT = (b"\r", b"\n")
ERASE = (b"\x7f", b"\x08")        # Backspace as terminals send it, and Ctrl-H
KILL_LINE = b"\x15"               # Ctrl-U

#: How long after an Esc to wait for the rest of an escape sequence. A terminal
#: sends a whole sequence in one write, so this only has to cover the relay.
SEQUENCE_WAIT = 0.05


def ask(label, stdin=None, stdout=None):
    """Show `label` and read one line. Returns the text, or None if cancelled.

    Without a terminal (tests, piped input) this falls back to reading a plain
    line, where end of input is the only way to cancel.

    Args:
        label (str): Prompt text written before input is read.
        stdin (TextIO or None): Input stream; None uses sys.stdin. A real TTY
            is temporarily put in cbreak mode and restored before returning.
        stdout (TextIO or None): Prompt and echo destination; None uses sys.stdout.

    Returns:
        str or None: Accepted text without its line ending, including an empty
            string; None for cancellation or end of input.

    Raises:
        OSError: Stream or terminal operations fail.
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stdout.write(label)
    stdout.flush()

    try:
        fd = stdin.fileno()
        if not os.isatty(fd):
            fd = None
    except (AttributeError, ValueError, OSError):
        fd = None
    if fd is None:
        line = stdin.readline()
        stdout.write("\n")
        return line.rstrip("\r\n") if line else None

    import termios
    import tty

    saved = termios.tcgetattr(fd)
    try:
        # cbreak, not raw: keystrokes arrive one at a time and unechoed, but
        # output processing stays on, so "\n" still returns the carriage.
        tty.setcbreak(fd)
        return read_line(
            read=lambda: os.read(fd, 1),
            pending=lambda: bool(select.select([fd], [], [], SEQUENCE_WAIT)[0]),
            write=lambda text: (stdout.write(text), stdout.flush()),
        )
    except KeyboardInterrupt:
        # cbreak keeps signals on, so Ctrl-C can arrive as SIGINT instead of a byte.
        stdout.write("\n")
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def read_line(read, pending, write):
    """The line editor itself, free of any terminal so it can be tested.

    Args:
        read (Callable[[], bytes]): Read one byte, or return b"" at end of input.
        pending (Callable[[], bool]): Indicate whether another byte is waiting,
            allowing escape sequences to be distinguished from a lone Esc.
        write (Callable[[str], object]): Echo text and line-editing control
            characters; its return value is ignored.

    Returns:
        str or None: Decoded UTF-8 text on Enter, or None for Esc, Ctrl-C,
            Ctrl-D, or end of input. Enter alone returns an empty string.
    """
    decode = codecs.getincrementaldecoder("utf-8")(errors="replace").decode
    chars = []
    while True:
        byte = read()
        if not byte or byte in CANCEL:
            write("\n")
            return None
        if byte in ACCEPT:
            write("\n")
            return "".join(chars)
        if byte == ESC:
            if not pending():
                write("\n")
                return None
            skip_sequence(read, pending)
            continue
        if byte in ERASE:
            if chars:
                chars.pop()
                write("\b \b")
            continue
        if byte == KILL_LINE:
            write("\b \b" * len(chars))
            del chars[:]
            continue
        if byte < b" ":
            continue  # any other control key: ignore rather than insert it

        text = decode(byte)  # "" until a multi-byte character is complete
        if text:
            chars.extend(text)
            write(text)


def skip_sequence(read, pending):
    """Consume the rest of an escape sequence that follows an Esc.

    CSI (`Esc [`) and SS3 (`Esc O`) sequences end at the first byte in
    0x40-0x7E; anything else after Esc is an Alt+key chord, one byte long.

    Args:
        read (Callable[[], bytes]): Read the next byte after the consumed Esc;
            b"" marks end of input.
        pending (Callable[[], bool]): Indicate whether more sequence bytes
            are available without an indefinite wait.
    """
    introducer = read()
    if introducer not in (b"[", b"O"):
        return
    while pending():
        byte = read()
        if not byte or b"\x40" <= byte <= b"\x7e":
            return
