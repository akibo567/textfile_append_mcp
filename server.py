#!/usr/bin/env python3
import json
import sys
from dataclasses import dataclass
from io import BufferedReader
from pathlib import Path
from typing import Any, Dict, Optional


SERVER_NAME = "textfile-append"
SERVER_VERSION = "0.1.0"
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2024-11-05")
DEBUG_LOG_PATH = Path(__file__).with_name("mcp_debug.log")


def debug_log(message: str) -> None:
    line = f"[textfile-append] {message}\n"
    try:
        with DEBUG_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass


def _read_json_line(stream: BufferedReader) -> Optional[bytes]:
    while True:
        line = stream.readline()
        if not line:
            return None
        debug_log("raw line=%r" % (line,))
        stripped = line.strip()
        if not stripped:
            continue
        return stripped


def _read_content_length_message(stream: BufferedReader, first_line: bytes) -> Optional[Dict[str, Any]]:
    content_length = None
    line = first_line

    while True:
        stripped = line.strip()
        if not stripped:
            break

        header = stripped.decode("utf-8")
        name, _, value = header.partition(":")
        if name.lower() == "content-length":
            content_length = int(value.strip())

        line = stream.readline()
        if not line:
            return None
        debug_log("raw line=%r" % (line,))

    if content_length is None:
        raise McpError(-32700, "Missing Content-Length header")

    body = stream.read(content_length)
    if not body:
        return None

    decoded = json.loads(body.decode("utf-8"))
    if isinstance(decoded, dict):
        debug_log("recv method=%s id=%r" % (decoded.get("method"), decoded.get("id")))
    else:
        debug_log("recv batch size=%d" % (len(decoded),))
    return decoded


class McpError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class AppendRequest:
    file_path: str
    text: str
    remove_lines_from_end: int = 0
    ensure_trailing_newline: bool = False


def read_message() -> Optional[Dict[str, Any]]:
    try:
        line = _read_json_line(sys.stdin.buffer)
        if line is None:
            debug_log("stdin reached EOF")
            return None

        if line.lower().startswith(b"content-length:"):
            return _read_content_length_message(sys.stdin.buffer, line)

        decoded = json.loads(line.decode("utf-8"))
        if isinstance(decoded, dict):
            debug_log("recv method=%s id=%r" % (decoded.get("method"), decoded.get("id")))
        else:
            debug_log("recv batch size=%d" % (len(decoded),))
        return decoded
    except json.JSONDecodeError as exc:
        raise McpError(-32700, f"Invalid JSON: {exc}") from exc


def write_message(message: Dict[str, Any]) -> None:
    debug_log(
        "send method=%s id=%r has_result=%s has_error=%s"
        % (
            message.get("method"),
            message.get("id"),
            "result" in message,
            "error" in message,
        )
    )
    payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()


def success(message_id: Any, result: Dict[str, Any]) -> None:
    write_message({"jsonrpc": "2.0", "id": message_id, "result": result})


def failure(message_id: Any, code: int, message: str) -> None:
    write_message(
        {
            "jsonrpc": "2.0",
            "id": message_id,
            "error": {"code": code, "message": message},
        }
    )


def parse_request(arguments: Dict[str, Any]) -> AppendRequest:
    file_path = arguments.get("file_path")
    text = arguments.get("text", "")
    remove_lines = arguments.get("remove_lines_from_end", 0)
    ensure_trailing_newline = arguments.get("ensure_trailing_newline", False)

    if not isinstance(file_path, str) or not file_path:
        raise McpError(-32602, "`file_path` must be a non-empty string")
    if not isinstance(text, str):
        raise McpError(-32602, "`text` must be a string")
    if not isinstance(remove_lines, int) or remove_lines < 0:
        raise McpError(-32602, "`remove_lines_from_end` must be an integer >= 0")
    if not isinstance(ensure_trailing_newline, bool):
        raise McpError(-32602, "`ensure_trailing_newline` must be a boolean")

    return AppendRequest(
        file_path=file_path,
        text=text,
        remove_lines_from_end=remove_lines,
        ensure_trailing_newline=ensure_trailing_newline,
    )


def resolve_path(file_path: str) -> Path:
    path = Path(file_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def compute_updated_text(original: str, text: str, remove_lines_from_end: int) -> str:
    if remove_lines_from_end == 0:
        return original + text

    lines = original.splitlines(keepends=True)
    if remove_lines_from_end >= len(lines):
        trimmed = ""
    else:
        trimmed = "".join(lines[:-remove_lines_from_end])
    return trimmed + text


def append_with_trim(request: AppendRequest) -> Dict[str, Any]:
    path = resolve_path(request.file_path)
    debug_log(
        "append file=%s remove_lines=%d text_len=%d ensure_nl=%s"
        % (
            path,
            request.remove_lines_from_end,
            len(request.text),
            request.ensure_trailing_newline,
        )
    )
    if not path.exists():
        raise McpError(-32000, f"File does not exist: {path}")
    if not path.is_file():
        raise McpError(-32000, f"Path is not a file: {path}")

    original = path.read_text(encoding="utf-8")
    updated = compute_updated_text(original, request.text, request.remove_lines_from_end)
    if request.ensure_trailing_newline and not updated.endswith("\n"):
        updated += "\n"

    path.write_text(updated, encoding="utf-8")

    return {
        "file_path": str(path),
        "removed_lines_from_end": request.remove_lines_from_end,
        "appended_text_length": len(request.text),
        "final_size_bytes": path.stat().st_size,
    }


def negotiate_protocol_version(requested_version: Any) -> str:
    if isinstance(requested_version, str) and requested_version in SUPPORTED_PROTOCOL_VERSIONS:
        return requested_version
    return SUPPORTED_PROTOCOL_VERSIONS[0]


def handle_initialize(message_id: Any, params: Dict[str, Any]) -> None:
    protocol_version = negotiate_protocol_version(params.get("protocolVersion"))
    success(
        message_id,
        {
            "protocolVersion": protocol_version,
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "capabilities": {
                "prompts": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
                "tools": {"listChanged": False},
            },
        },
    )


def handle_tools_list(message_id: Any) -> None:
    success(
        message_id,
        {
            "tools": [
                {
                    "name": "append_text_with_tail_trim",
                    "description": (
                        "Remove N lines from the end of a text file, then append the given text."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Target file path. Relative paths are resolved from the server working directory.",
                            },
                            "text": {
                                "type": "string",
                                "default": "",
                                "description": "Text to append after trimming.",
                            },
                            "remove_lines_from_end": {
                                "type": "integer",
                                "minimum": 0,
                                "default": 0,
                                "description": "Number of lines to remove from the end of the file before appending.",
                            },
                            "ensure_trailing_newline": {
                                "type": "boolean",
                                "default": False,
                                "description": "If true, ensure the final file ends with a newline.",
                            },
                        },
                        "required": ["file_path"],
                        "additionalProperties": False,
                    },
                }
            ]
        },
    )


def handle_prompts_list(message_id: Any) -> None:
    success(message_id, {"prompts": []})


def handle_resources_list(message_id: Any) -> None:
    success(message_id, {"resources": []})


def handle_tools_call(message_id: Any, params: Dict[str, Any]) -> None:
    name = params.get("name")
    arguments = params.get("arguments", {})

    if name != "append_text_with_tail_trim":
        raise McpError(-32601, f"Unknown tool: {name}")
    if not isinstance(arguments, dict):
        raise McpError(-32602, "`arguments` must be an object")

    request = parse_request(arguments)
    result = append_with_trim(request)

    success(
        message_id,
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, ensure_ascii=False),
                }
            ]
        },
    )


def handle_message(message: Dict[str, Any]) -> None:
    method = message.get("method")
    message_id = message.get("id")
    params = message.get("params", {})

    if method == "initialize":
        if not isinstance(params, dict):
            raise McpError(-32602, "`params` must be an object")
        handle_initialize(message_id, params)
        return
    if method == "ping":
        success(message_id, {})
        return
    if method == "initialized":
        return
    if method == "notifications/initialized":
        return
    if method == "tools/list":
        handle_tools_list(message_id)
        return
    if method == "prompts/list":
        handle_prompts_list(message_id)
        return
    if method == "resources/list":
        handle_resources_list(message_id)
        return
    if method == "tools/call":
        if not isinstance(params, dict):
            raise McpError(-32602, "`params` must be an object")
        handle_tools_call(message_id, params)
        return

    if message_id is not None:
        raise McpError(-32601, f"Method not found: {method}")


def process_incoming_message(message: Any) -> None:
    if isinstance(message, list):
        if not message:
            raise McpError(-32600, "Invalid request: empty batch")
        for item in message:
            if not isinstance(item, dict):
                failure(None, -32600, "Invalid request: batch item must be an object")
                continue
            try:
                handle_message(item)
            except McpError as exc:
                failure(item.get("id"), exc.code, exc.message)
            except Exception as exc:
                debug_log(f"internal error in batch item: {exc!r}")
                failure(item.get("id"), -32603, f"Internal error: {exc}")
        return

    if not isinstance(message, dict):
        raise McpError(-32600, "Invalid request: message must be an object")

    handle_message(message)


def main() -> int:
    debug_log("server starting")
    while True:
        try:
            debug_log("Running")
            message = read_message()
            if message is None:
                debug_log("stdin closed")
                return 0
            process_incoming_message(message)
        except McpError as exc:
            message_id = None
            if "message" in locals() and isinstance(message, dict):
                message_id = message.get("id")
            debug_log(f"mcp error code={exc.code} message={exc.message}")
            failure(message_id, exc.code, exc.message)
        except Exception as exc:
            message_id = None
            if "message" in locals() and isinstance(message, dict):
                message_id = message.get("id")
            debug_log(f"internal error: {exc!r}")
            failure(message_id, -32603, f"Internal error: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
