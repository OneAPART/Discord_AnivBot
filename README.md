# 🎉 AnniversaryBot

Discord ユーザーの **誕生日** と **活動記念日** を、毎日 JST 00:00 に自動でお祝いする常駐型 Discord Bot です。
従来の Google Apps Script + スプレッドシート + Webhook 構成から、`discord.py` + SQLite による自己完結型へ移行したものです。

---

## ✨ 主な機能

| 機能 | コマンド | 説明 |
|------|---------|------|
| プロフィール登録 / 編集 | `/profile [user]` | Modal フォームで一括入力。`user` を指定すると他ユーザーを代理登録できます（要オーナー権限・既定）。誕生日・活動開始日・`Twitter ID` はいずれも**任意**。既存値はプリフィルされます。**サーバーごとに独立して保持** されます。 |
| プロフィール削除 | `/profile_delete [user]` | このサーバーからプロフィールを削除します。 |
| プロフィール表示 | `/show [user] [public]` | 自分または指定ユーザーの情報を Embed 表示。既定では**自分にしか見えません** (ephemeral)。`public:True` でチャンネル公開表示。Twitter 未登録でも崩れません。 |
| プロフィール一覧 | `/list [sort] [public]` | 当サーバー所属の登録ユーザー一覧。`name` / `birthday` / `anniversary` で並び替え可、ページャー付き。既定では自分にしか見えません (ephemeral)。`public:True` でチャンネル公開表示。 |
| 通知チャンネル設定 | `/config channel <channel>` | お祝い投稿先をサーバーごとに設定（要 `サーバー管理` 権限）。 |
| 不在ユーザー通知設定 | `/config absent <true\|false>` | サーバーに不在のユーザーを通知するか切り替え。既定は `false`（在籍者のみ通知）。 |
| アバター取得元設定 | `/config avatar <twitter\|discord>` | 通知カード右上に表示するアバターをどちらを優先して取得するか設定。既定は `twitter`。未登録 / 取得不能時はもう一方へフォールバック。 |
| 権限設定 | `/config permission <command> <mode> [role1..3]` | コマンド実行権限を `owner` / `everyone` / `role` から選択（要 `サーバー管理` 権限）。 |
| 設定確認 | `/config show` | 通知チャンネルとコマンド権限の現状を一覧表示。 |
| 自動通知 | （自動） | 毎日 **JST 00:00** に誕生日・活動記念日を投稿。記念日は「○周年」を自動計算。 |

すべての通知 / プロフィール表示には Twitter プロフィールへ即座に飛べる **リンクボタン** が付きます（登録している場合のみ）。

---

## 🛠 動作環境

- Python **3.10 以上**
- 依存ライブラリ（[requirements.txt](requirements.txt)）
  - `discord.py >= 2.3`
  - `aiosqlite >= 0.19`
  - `python-dotenv >= 1.0`

---

## 📁 ディレクトリ構成

```
AnniversaryBot/
├── main.py                 # エントリポイント / Bot 初期化 / コマンド同期
├── requirements.txt
├── .env.example            # 環境変数テンプレート
├── .gitignore
├── db/
│   └── database.py         # aiosqlite による非同期 DAO + スキーマ
├── cogs/
│   ├── profile_cog.py      # /profile, /show, /list, /profile_delete
│   ├── config_cog.py       # /config channel, permission, absent, avatar, show
│   ├── admin_cog.py        # /admin trigger, next_run, sync
│   └── anniversary_cog.py  # tasks.loop による JST 00:00 通知
├── ui/
│   └── modals.py           # ProfileModal + Twitter リンクボタン View
├── utils/
│   ├── validators.py       # 日付・Twitter ID パース / バリデーション
│   ├── permissions.py      # コマンド権限判定
│   ├── avatar.py           # アバター URL 解決 (X / Discord)
│   └── error_notifier.py   # エラー通知 Webhook (HTTP POST)
└── scripts/
    ├── clear_global_commands.py  # グローバル登録を一括削除するワンショット
    └── clear_guild_commands.py   # 特定ギルドの登録を一括削除するワンショット
```

---

## 🚀 セットアップ

### 1. リポジトリ取得 & 仮想環境

```powershell
git clone <this-repo-url> AnniversaryBot
cd AnniversaryBot

python -m venv venv
.\venv\Scripts\Activate.ps1   # macOS/Linux: source venv/bin/activate
```

### 2. 依存ライブラリのインストール

```powershell
pip install -r requirements.txt
```

### 3. Discord Developer Portal の設定

1. <https://discord.com/developers/applications> でアプリケーションを作成。
2. **Bot** タブで Bot を作成し、**Token** を控える。
3. 以下の **Privileged Gateway Intents** を ON にする。
   - ✅ `SERVER MEMBERS INTENT` （ギルド所属判定で使用）
4. **OAuth2 → URL Generator** で次のスコープと権限を選択し、生成された URL でサーバーへ招待。
   - スコープ: `bot`, `applications.commands`
   - 権限: `View Channels`, `Send Messages`, `Embed Links`, `Mention Everyone`（必要に応じて）

https://discord.com/oauth2/authorize?client_id=1500859368399306863&permissions=150528&integration_type=0&scope=bot+applications.commands

### 4. 環境変数の設定

`.env.example` をコピーして `.env` を作成し、自分の値を記入してください。

```
DISCORD_TOKEN=（Developer Portal で取得した Bot トークン）
TEST_GUILD_ID=（任意: テストサーバーの ID。指定するとそのサーバーへ即時同期）
DB_PATH=anniversary.db
ENV_NAME=development             # 任意。エラー通知 JSON の "env" になります
ERROR_WEBHOOK_URL=               # 任意。未設定ならコード内デフォルトの Power Automate URL へ送信。後述「エラー通知 Webhook」参照
```

> ⚠️ `.env` は **絶対にコミットしないでください**（`.gitignore` 済）。
> もし誤ってトークンを公開してしまった場合は、Developer Portal から **Reset Token** で必ず再発行してください。

### 5. 起動

```powershell
python main.py
```

初回起動時に `anniversary.db` が自動生成され、必要なテーブルが作成されます。

---

## 💡 使い方

### プロフィール登録

1. サーバーで `/profile` を実行。
2. 表示された Modal に入力して送信。

| 項目 | 形式 | 例 | 必須 |
|------|------|-----|------|
| 表示名 | 自由文字列（最大64） | `たろう` | ✅ |
| Twitter ID | `@username`（半角英数+`_`、最大15） | `@example_user` | 任意 |
| 誕生日 | `MM/DD`（空欄で未登録） | `04/15` | 任意 |
| 活動開始日 | `YYYY/MM/DD`（空欄で未登録） | `2018/04/15` | 任意 |

> 区切り文字は `/` `-` `.` のいずれも受け付けます（例: `2018-04-15`）。
> うるう年・月別最大日数も自動チェックします。
> 誕生日 / 活動開始日 / Twitter ID はいずれも**未登録可**で、未登録項目は表示・一覧・通知で自動的にスキップされます。

### プロフィール確認

```
/show                              # 自分のプロフィール（自分にしか見えない）
/show user:@たろう                  # 他のメンバーのプロフィール
/show user:@たろう public:True       # チャンネルに公開して表示
```

- 既定は **ephemeral**（実行者にしか見えない）。`public:True` を付けるとチャンネルに公開されます。
- Twitter / 誕生日 / 活動開始日が未登録の項目は自動で非表示になります。

### 通知チャンネル設定（管理者向け）

```
/config channel channel:#general
```

- 実行には **サーバー管理** 権限が必要です。
- 設定したチャンネルに Bot が `メッセージを送信` / `埋め込みリンク` 権限を持っているか自動チェックします。

### 不在ユーザーへの通知設定

登録済みだがサーバーを退出済みのユーザーに対する振る舞いを切り替えられます。

```
/config absent notify:False    # サーバー在籍メンバーのみ通知 (既定)
/config absent notify:True     # 不在ユーザーにも通知する (旧振る舞い)
```

- `False` (既定): そのサーバーのメンバー一覧に含まれていないユーザーはスキップされるため、退出した人の誕生日メンションが連連受したりしません。
- `True`: 登録されているユーザー全員を通知します。
- 事前に `/config channel` でチャンネルを設定している必要があります。
- Bot 側でメンバー一覧を取得できない（`Server Members Intent` 未許可等）場合は、`False` 設定下では安全側で送信をスキップします。

### コマンド権限の制御（管理者向け）

`/profile` `/show` `/list` の各コマンドに対して、サーバーごとに実行可否を設定できます。

```
/config permission command:<profile|show|list> mode:<owner|everyone|role> [role1] [role2] [role3]
```

| モード | 意味 |
|--------|------|
| `owner` | サーバーオーナーのみ実行可（**既定**） |
| `everyone` | 全員実行可 |
| `role` | 指定ロール（最大3つ）のいずれかを保持しているメンバーのみ実行可 |

例:

```
/config permission command:list mode:role role1:@運営
/config permission command:profile mode:everyone   # 全員に自分のプロフィール登録を許可
/config permission command:show mode:owner
```

> 💡 **既定はオーナーのみ** です。一般メンバーに `/profile` `/show` `/list` を使わせたい場合は上記のように `everyone` または `role` を明示的に設定してください。

現在の設定確認:

```
/config show
```

> ℹ️ `/config` 自体は常に Discord の **サーバー管理** 権限が必要で、上記の権限制御の対象外です。

### 一覧表示

```
/list                              # 名前順（自分にしか見えない）
/list sort:birthday                # 誕生日順 (1/1 → 12/31)
/list sort:anniversary             # 活動開始日順 (古い順)
/list public:True                  # チャンネルに公開して表示
```

- 既定は **ephemeral**（実行者にしか見えない）。`public:True` を付けるとチャンネルに公開されます。
- 当サーバーに所属している **かつ** プロフィール登録済みのメンバーのみ表示されます。
- 1 ページ 10 件。`◀ 前へ` `次へ ▶` ボタンでページ送り（実行者のみ操作可、3 分でタイムアウト）。

### 自動通知

設定後は何もする必要はありません。毎日 **JST 00:00** に以下を自動投稿します。

- 🎂 **誕生日** が今日のメンバーへお祝いメッセージ
- 🎉 **活動記念日** が今日のメンバーへ「○周年」表記付きメッセージ

メンションされた本人へ Embed と（登録されていれば）Twitter ボタンが届きます。誕生日 / 活動開始日が未登録のユーザーはそもそも通知対象になりません（「準備中」用途に便利）。

#### カード右上のアバター表示

通知カードの右上 (Embed thumbnail) にアバター画像を表示します。`/config avatar` で取得元を切り替えられます。

| 設定 | 動作 |
|------|------|
| `twitter`（既定） | X(Twitter) アバターを優先。Twitter ID 未登録のときは Discord アバターにフォールバック。 |
| `discord` | Discord アバターを優先。サーバーに本人が不在などで取得できないときは X アバターにフォールバック。 |

> X アバターの取得には [unavatar.io](https://unavatar.io/) を使用しています (`https://unavatar.io/x/<handle>`)。API キー不要で、取得できない場合は unavatar.io 側のフォールバック画像が表示されます。

---

## 🗄 データベース

SQLite ファイル（既定: `anniversary.db`）にすべて保存されます。

### `user_profiles`

プロフィールはサーバー単位で管理されます。同一ユーザーでもサーバーが違えば別レコードです。

| カラム | 型 | 備考 |
|--------|----|------|
| `guild_id` | INTEGER | 複合主キー (Discord Guild ID) |
| `user_id` | INTEGER | 複合主キー (Discord User ID) |
| `name` | TEXT | 表示名 |
| `twitter_id` | TEXT | `@handle` 形式（NULL 可） |
| `birth_month` / `birth_day` | INTEGER | 誕生月日（NULL 可） |
| `start_year` / `start_month` / `start_day` | INTEGER | 活動開始日（NULL 可） |
| `updated_at` | TIMESTAMP | 自動更新 |

> ⚠️ **旧バージョンからアップグレードした場合**: 旧スキーマの `user_profiles` は起動時に自動的に `_legacy_user_profiles` にリネームされ、退避されます。所属サーバーが特定できないため自動移行はされません。各サーバーで `/profile` を再登録するか、必要なら `_legacy_user_profiles` から手動で SQL でコピーしてください。

### `server_settings`

| カラム | 型 | 備考 |
|--------|----|------|
| `guild_id` | INTEGER | PRIMARY KEY |
| `channel_id` | INTEGER | 通知投稿チャンネル |
| `notify_absent` | INTEGER | 0=不在ユーザーを通知しない (既定) / 1=通知する |
| `avatar_source` | TEXT | `twitter` (既定) / `discord`。通知カードアバターの優先取得元 |
| `updated_at` | TIMESTAMP | 自動更新 |

### `command_permissions`

| カラム | 型 | 備考 |
|--------|----|------|
| `guild_id` | INTEGER | 複合主キー |
| `command_name` | TEXT | 複合主キー（`profile` / `show` / `list`） |
| `mode` | TEXT | `owner` / `everyone` / `role` |
| `role_ids` | TEXT | `role` モード時の許可ロール ID（カンマ区切り） |
| `updated_at` | TIMESTAMP | 自動更新 |

### バックアップ

```powershell
Copy-Item anniversary.db anniversary.db.bak
```

Bot 停止中に行うのが安全です。

---

## 🧰 運用 Tips

- **常駐運用**: `pm2` / `systemd` / Windows サービス（NSSM）/ Docker などでプロセスを保持してください。
- **ログ**: 標準出力に `INFO` レベルで出力されます。リダイレクトしてファイル保存を推奨。
  ```powershell
  python main.py *>> bot.log
  ```
- **タイムゾーン**: コード内で **JST 固定**（`utils/`・`cogs/anniversary_cog.py`）。サーバー OS の TZ には依存しません。
- **コマンド同期**: `TEST_GUILD_ID` 指定時は即時、未指定（グローバル同期）時は反映に最大 1 時間程度かかります。

---

## 🧪 動作試験

### A. 自動テスト（pytest）

DB / バリデーション / 権限判定 / 一覧ソート / 通知ロジックの集計までをユニットテストでカバーしています。

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

テスト構成（[tests/](tests/)）：

| ファイル | 内容 |
|---------|------|
| [tests/test_validators.py](tests/test_validators.py) | 日付・Twitter ID パース |
| [tests/test_database.py](tests/test_database.py) | upsert / 検索 / 権限 / 一覧 |
| [tests/test_permissions.py](tests/test_permissions.py) | owner / everyone / role 判定 |
| [tests/test_sort.py](tests/test_sort.py) | `/list` ソートキー |
| [tests/test_anniversary.py](tests/test_anniversary.py) | 通知の対象抽出と配信回数 |

### B. 試験用 Bot で本番同等の手動テスト

1. **テスト専用** の Discord アプリケーションを Developer Portal で別途作成（本番トークンを使い回さない）。
2. プライベートサーバーを 1 つ用意し、`bot` + `applications.commands` スコープで招待。
3. `.env` の `DISCORD_TOKEN` をテスト用に差し替え、`TEST_GUILD_ID` にそのサーバーの ID を入れて `python main.py` を起動（即時にコマンドが反映される）。
4. 下記シナリオを順に実施。

#### シナリオ表

| # | 手順 | 期待結果 |
|---|------|---------|
| 1 | `/profile` を実行し Modal を送信 | 「保存しました」が表示され、DB に行が増える |
| 2 | 不正値 (例: 誕生日に `13/40`) で送信 | 入力エラーメッセージが表示される |
| 2b | 誕生日・活動開始日を空欄で送信 | エラーにならず保存され、`/show` でその項目が非表示 |
| 3 | `/show` を実行 | 自分にしか見えない (ephemeral) Embed が出る |
| 3b | `/show public:True` | チャンネルに公開される |
| 3c | Twitter 未登録のユーザーを `/show` | Twitter フィールド・ボタンが出ず、エラーも出ない |
| 4 | `/show user:@他人` | 他人の情報が出る、未登録なら未登録メッセージ |
| 5 | `/list sort:birthday` | 月日順に並び、ページネーションが動く（既定 ephemeral） |
| 5b | `/list public:True` | チャンネルに公開される |
| 6 | `/config channel #任意` | 通知チャンネルが保存される |
| 7 | `/config permission command:list mode:role role1:@テストロール` | ロール未保有メンバーで `/list` が拒否される |
| 8 | `/config permission command:profile mode:owner` | オーナー以外で `/profile` が拒否される |
| 9 | `/config show` | 現在の設定がすべて見える |
| 10 | `/profile user:@他人`（オーナーで実行） | 代理登録できるモーダルタイトルに対象名が出る |
| 11 | `/config avatar source:twitter` 後に `/admin trigger` | 通知カード右上に X(Twitter) のアバター画像が表示される |
| 12 | `/config avatar source:discord` 後に `/admin trigger` | 通知カード右上に Discord のアバター画像が表示される |
| 13 | Twitter 未登録ユーザーで `source:twitter` で通知 | Discord アバターへフォールバックされる |

### C. 通知タスクの即時試験

24 時間待たずに通知ロジックを発火させるためのオーナー専用コマンドを用意してあります（[cogs/admin_cog.py](cogs/admin_cog.py)）。

```
/admin trigger                                # 今日(JST)で即時実行
/admin trigger date_str:2026-04-15            # 任意日付で実行
/admin trigger date_str:2026-04-15 dry_run:True   # 送信せず対象だけ確認
/admin next_run                               # 次回 daily_notify の発火予定
/admin sync                                   # このサーバーへスラッシュコマンドを即時同期
/admin sync scope:global                      # 全サーバーへ反映 (最大1時間)
/admin sync clear:True                        # このサーバー登録分を一旦消してから同期
```

> 💡 **コマンドの新オプションが反映されない時** は `/admin sync` をオーナー権限で実行してください。`scope:guild` (既定) なら **即時** に当サーバーへ反映されます。`scope:global` は全サーバーに反映されますが Discord のキャッシュ都合で各クライアントへの反映に最大 1 時間かかります。

推奨手順：

1. 自分のプロフィールを `/profile` で登録（誕生日・活動開始日を「明日」など適当な値に）
2. `/admin trigger date_str:<明日の日付>` で発火
3. `/config channel` で設定したチャンネルに Embed が届くこと、`@メンション` 付き、Twitter ボタン付きであることを確認
4. `dry_run:True` で対象抽出のみ確認することも可

### D. 補助デバッグ

- ログレベルは `INFO`。発火・対象件数・送信失敗はすべてログに残ります。詳しく見たい場合は [main.py](main.py) の `logging.basicConfig` を `DEBUG` に変更してください。
- DB の中身を直接確認する場合：
  ```powershell
  sqlite3 anniversary.db ".dump user_profiles"
  sqlite3 anniversary.db "SELECT * FROM command_permissions;"
  ```

---

## 🐛 トラブルシューティング

| 症状 | 対処 |
|------|------|
| `/profile` などが Discord に表示されない | グローバル同期は時間がかかります。`.env` の `TEST_GUILD_ID` にテストサーバー ID を入れて再起動してください。 |
| 通知が来ない | 1) `/config channel` が設定済みか確認 / 2) Bot にチャンネル送信権限があるか / 3) Bot プロセスが 24h 起動継続しているか / 4) `Server Members Intent` が ON か |
| `DISCORD_TOKEN が未設定です` | `.env` が無い、またはキー名が違います。`.env.example` を参照。 |
| 入力エラーで Modal が弾かれる | 月日は `MM/DD`、活動開始日は `YYYY/MM/DD`。Twitter ID は `@英数_` のみ（最大15文字）。 |
| 「このコマンドを実行できるロールを持っていません」と出る | 管理者に `/config permission` の設定を確認してもらってください。`/config show` で現状確認できます。 |
| 同じスラッシュコマンドが二重に表示される | グローバル登録とギルド登録が両方残っています。`scripts/clear_global_commands.py --yes`（グローバル全削除）または `scripts/clear_guild_commands.py --yes`（テストギルド全削除）を実行 → `python main.py` で再起動して再登録してください。詳細は次節「コマンド同期スクリプト」参照。 |
| トークンを誤って公開した | 直ちに Developer Portal で **Reset Token** → 新しいトークンを `.env` に再設定。 |

---

## 🧹 コマンド同期スクリプト

[scripts/](scripts/) に、スラッシュコマンドの登録状態をクリーンアップするためのワンショットスクリプトを用意しています。

| スクリプト | 用途 | 反映 |
|---|---|---|
| `scripts/clear_global_commands.py` | **グローバル登録**を全削除 | 各クライアントへの反映に最大 1 時間 |
| `scripts/clear_guild_commands.py`  | 指定ギルド（既定は `.env` の `TEST_GUILD_ID`）の登録を全削除 | **即時** |

実行例:

```powershell
# 安全のため --yes が必須
.\venv\Scripts\python.exe scripts\clear_global_commands.py --yes
.\venv\Scripts\python.exe scripts\clear_guild_commands.py --yes
.\venv\Scripts\python.exe scripts\clear_guild_commands.py --yes --guild 1234567890123456789
```

実行後はそのまま `python main.py` で起動すれば、ソースの定義から再登録されます（`TEST_GUILD_ID` 設定下なら即時にギルドへ）。サーバーオーナーであれば、わざわざスクリプトを実行せず Discord 上から `/admin sync clear:True` でも同等のことができます。

---

## 🤷‍♀️ エラー通知 Webhook

本稿において設定されているのは、開発者向けの記述です。
変更された場合、開発者側で修正処理を行うことができないため十分ご注意ください。
未捕捉エラーや `logger.exception` で記録された **ERROR 以上のログ** を、指定 URL に JSON で POST します。

- 送信先の優先順位:
  1. `.env` の `ERROR_WEBHOOK_URL`（設定されていればこちら）
  2. 未設定の場合は [main.py](main.py) にハードコードされた **Power Automate トリガー URL** が使われます。
- 送信完全に無効化したい場合は [main.py](main.py) の `_DEFAULT_ERROR_WEBHOOK_URL` を空文字列に置き換えてください。

Sentry / Slack 互換 / Discord Webhook をそのまま受けることはできません（汎用 JSON のため）。受け先には次のような **任意 JSON を受け取れるエンドポイント** を指定してください。

- **Power Automate**「When a HTTP request is received」トリガー（約下のスキーマを貼り付ける）
- 自前 API / Cloudflare Worker / AWS Lambda Function URL
- iPaaS（[Pipedream](https://pipedream.com/) / [n8n](https://n8n.io/) / [Make](https://www.make.com/) / Zapier の Webhook）
- 動作確認用の [webhook.site](https://webhook.site/)

### リクエスト

- メソッド: `POST`
- ヘッダ: `Content-Type: application/json`
- タイムアウト: 5 秒（失敗しても Bot 動作には影響しません）

### JSON スキーマ

```json
{
  "type": "object",
  "required": ["bot", "level", "timestamp", "message"],
  "properties": {
    "bot":       { "type": "string",  "const": "AnniversaryBot" },
    "env":       { "type": "string",  "description": ".env の ENV_NAME (未設定なら 'unknown')" },
    "level":     { "type": "string",  "enum": ["ERROR", "CRITICAL"] },
    "timestamp": { "type": "string",  "format": "date-time", "description": "UTC ISO 8601 (末尾 Z)" },
    "logger":    { "type": "string",  "description": "Python logger 名" },
    "message":   { "type": "string" },
    "exception": {
      "oneOf": [
        { "type": "null" },
        {
          "type": "object",
          "required": ["type", "message", "traceback"],
          "properties": {
            "type":      { "type": "string", "description": "例外クラス名" },
            "message":   { "type": "string", "description": "str(exception)" },
            "traceback": { "type": "string", "description": "完全なトレースバック (最大約 6KB で打ち切り)" }
          }
        }
      ]
    },
    "context": {
      "type": "object",
      "description": "任意の追加情報。コマンド由来エラーでは下記キーが入ります。",
      "properties": {
        "guild_id":   { "type": ["integer", "null"] },
        "channel_id": { "type": ["integer", "null"] },
        "user_id":    { "type": ["integer", "null"] },
        "command":    { "type": ["string",  "null"] },
        "module":     { "type": "string" },
        "func":       { "type": "string" }
      }
    }
  }
}
```

### サンプルペイロード

```json
{
  "bot": "AnniversaryBot",
  "env": "production",
  "level": "ERROR",
  "timestamp": "2026-05-05T03:21:48.512Z",
  "logger": "anniversarybot",
  "message": "Unhandled app command error: AttributeError",
  "exception": {
    "type": "AttributeError",
    "message": "'NoneType' object has no attribute 'foo'",
    "traceback": "Traceback (most recent call last):\n  File ...\nAttributeError: ..."
  },
  "context": {
    "guild_id": 1486024857043861504,
    "channel_id": 1500000000000000000,
    "user_id": 200,
    "command": "show"
  }
}
```

---

## �📜 ライセンス

社内 / 個人利用想定。必要に応じて追記してください。
