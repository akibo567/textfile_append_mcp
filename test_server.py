import tempfile
import unittest
from pathlib import Path

from server import (
    AppendRequest,
    append_with_trim,
    compute_updated_text,
    negotiate_protocol_version,
    parse_request,
)


class ComputeUpdatedTextTests(unittest.TestCase):
    def test_append_without_removal(self) -> None:
        self.assertEqual(compute_updated_text("a\nb\n", "c\n", 0), "a\nb\nc\n")

    def test_remove_one_line_then_append(self) -> None:
        self.assertEqual(compute_updated_text("a\nb\n", "c\n", 1), "a\nc\n")

    def test_remove_more_lines_than_exist(self) -> None:
        self.assertEqual(compute_updated_text("a\n", "c\n", 5), "c\n")

    def test_last_line_without_trailing_newline_is_removed(self) -> None:
        self.assertEqual(compute_updated_text("a\nb", "c", 1), "a\nc")


class AppendWithTrimTests(unittest.TestCase):
    def test_write_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sample.txt"
            path.write_text("hello\nworld\n", encoding="utf-8")

            result = append_with_trim(
                AppendRequest(
                    file_path=str(path),
                    text="tail\n",
                    remove_lines_from_end=1,
                )
            )

            self.assertEqual(path.read_text(encoding="utf-8"), "hello\ntail\n")
            self.assertEqual(result["removed_lines_from_end"], 1)

    def test_ensure_trailing_newline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sample.txt"
            path.write_text("hello", encoding="utf-8")

            append_with_trim(
                AppendRequest(
                    file_path=str(path),
                    text=" world",
                    ensure_trailing_newline=True,
                )
            )

            self.assertEqual(path.read_text(encoding="utf-8"), "hello world\n")


class ParseRequestTests(unittest.TestCase):
    def test_text_defaults_to_empty_string_when_omitted(self) -> None:
        request = parse_request({"file_path": "/tmp/example.txt"})

        self.assertEqual(request.text, "")
        self.assertEqual(request.remove_lines_from_end, 0)
        self.assertFalse(request.ensure_trailing_newline)


class ProtocolTests(unittest.TestCase):
    def test_supported_protocol_is_echoed(self) -> None:
        self.assertEqual(negotiate_protocol_version("2025-06-18"), "2025-06-18")

    def test_unknown_protocol_falls_back_to_latest_supported(self) -> None:
        self.assertEqual(negotiate_protocol_version("2099-01-01"), "2025-06-18")


if __name__ == "__main__":
    unittest.main()
