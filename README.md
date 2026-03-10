# textfile_append_mcp

指定したテキストファイルに対して、末尾から任意の行数を削除してから新しいテキストを追記するMCPサーバーです。

## 仕様

ツール名: `append_text_with_tail_trim`

引数:

- `file_path` (`string`, 必須): 対象ファイルのパス
- `text` (`string`, 任意, デフォルト `""`): 追記する文字列
- `remove_lines_from_end` (`integer`, 任意, デフォルト `0`): 末尾から削除する行数
- `ensure_trailing_newline` (`boolean`, 任意, デフォルト `false`): 最終的にファイル末尾を改行で終わらせる

動作:

1. 対象ファイルを UTF-8 で読み込む
2. 末尾から `remove_lines_from_end` 行を削除する
3. `text` を末尾に追加する
4. 必要なら最後に改行を付与する

注意:

- ファイルが存在しない場合はエラーになります
- 相対パスはサーバーのカレントディレクトリ基準で解決されます
- 削除行数がファイル行数を超えた場合は、空文字にしたあとで `text` を追記します

## 実行

```bash
python3 server.py
```

## テスト

```bash
python3 -m unittest test_server.py
```

## MCPクライアント設定例

```json
{
  "mcpServers": {
    "textfile-append": {
      "command": "python3",
      "args": ["server.py"],
      "cwd": "[このmcpのあるディレクトリの絶対パス]",
      "trust": true
    }
  }
}
```

###Codexの場合(プロジェクトの.codex/setting.tomlで設定を推奨)
```
[mcp_servers.textfile_append]
command = "/usr/bin/python3"
args = ["[このMCPサーバープロジェクトの絶対パス]/server.py"]
cwd = "[利用プロジェクトトップの絶対パス]"
required = true
```
