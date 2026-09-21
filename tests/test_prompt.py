"""The popup line editor: keys in, text (or a cancel) out."""
import io
import unittest

import support  # noqa: F401  (puts the plugin root on sys.path)

from myherdr import prompt


def type_keys(data):
    """Run read_line over `data` as if typed. Returns (result, echoed text)."""
    stream = io.BytesIO(data)
    echoed = []

    def pending():
        # Mirrors a real terminal: the rest of an escape sequence arrives in
        # the same write, a lone Esc is followed by nothing.
        return stream.tell() < len(data)

    result = prompt.read_line(read=lambda: stream.read(1), pending=pending,
                              write=echoed.append)
    return result, "".join(echoed)


class ReadLineTest(unittest.TestCase):
    def test_enter_accepts_the_line(self):
        self.assertEqual(type_keys(b"spike\r")[0], "spike")
        self.assertEqual(type_keys(b"spike\n")[0], "spike")

    def test_enter_on_nothing_is_an_empty_name_not_a_cancel(self):
        self.assertEqual(type_keys(b"\r")[0], "")

    def test_what_is_typed_is_echoed(self):
        self.assertEqual(type_keys(b"ab\r")[1], "ab\n")

    def test_esc_cancels(self):
        self.assertIsNone(type_keys(b"half a na\x1b")[0])

    def test_ctrl_c_and_ctrl_d_cancel(self):
        self.assertIsNone(type_keys(b"abc\x03")[0])
        self.assertIsNone(type_keys(b"abc\x04")[0])

    def test_end_of_input_cancels(self):
        self.assertIsNone(type_keys(b"abc")[0])

    def test_arrow_keys_are_not_a_cancel(self):
        # Esc [ D is Left: it starts with Esc but is one key, not Esc.
        self.assertEqual(type_keys(b"ab\x1b[Dc\r")[0], "abc")
        self.assertEqual(type_keys(b"ab\x1bOAc\r")[0], "abc")

    def test_longer_sequences_are_swallowed_whole(self):
        # Ctrl+Right: Esc [ 1 ; 5 C
        self.assertEqual(type_keys(b"a\x1b[1;5Cb\r")[0], "ab")

    def test_alt_chords_are_swallowed(self):
        self.assertEqual(type_keys(b"a\x1bxb\r")[0], "ab")

    def test_backspace_erases(self):
        result, echoed = type_keys(b"abx\x7fc\r")
        self.assertEqual(result, "abc")
        self.assertIn("\b \b", echoed)
        self.assertEqual(type_keys(b"abx\x08c\r")[0], "abc")

    def test_backspace_on_an_empty_line_does_nothing(self):
        result, echoed = type_keys(b"\x7f\x7fa\r")
        self.assertEqual(result, "a")
        self.assertNotIn("\b", echoed)

    def test_ctrl_u_clears_the_line(self):
        self.assertEqual(type_keys(b"wrong\x15right\r")[0], "right")

    def test_other_control_keys_are_ignored(self):
        self.assertEqual(type_keys(b"a\x01\x0bb\tc\r")[0], "abc")

    def test_multibyte_characters_arrive_whole(self):
        result, echoed = type_keys("tür ✓\r".encode("utf-8"))
        self.assertEqual(result, "tür ✓")
        self.assertEqual(echoed, "tür ✓\n")

    def test_backspace_removes_a_whole_multibyte_character(self):
        self.assertEqual(type_keys("aü\x7f\r".encode("utf-8"))[0], "a")


class AskTest(unittest.TestCase):
    """Without a terminal, ask() reads a plain line: what tests and pipes get."""

    def test_reads_a_line_and_shows_the_label(self):
        out = io.StringIO()
        self.assertEqual(prompt.ask("Name: ", io.StringIO("spike\n"), out), "spike")
        self.assertTrue(out.getvalue().startswith("Name: "))

    def test_end_of_input_is_a_cancel(self):
        self.assertIsNone(prompt.ask("Name: ", io.StringIO(""), io.StringIO()))

    def test_an_empty_line_is_an_empty_name(self):
        self.assertEqual(prompt.ask("Name: ", io.StringIO("\n"), io.StringIO()), "")


if __name__ == "__main__":
    unittest.main()
