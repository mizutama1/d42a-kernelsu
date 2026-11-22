# ログ

## 2026-11-23 04:0x プロジェクト作成
- d42a-kernelsu-official を新規作成、純正素材をコピー
- apply_ksu_hooks.py を作成し、抽出済み 4.14 ソースで適用・冪等性を確認
- build.sh / workflow を作成

## 修正 1: 本家 v0.9.5 は KPROBES=y なら kprobe フックのみで動く
- `ksu_execveat_hook` / `ksu_vfs_read_hook` は `#ifndef CONFIG_KPROBES` の時だけ定義される
  → KPROBES=y では manual hook パッチを当ててはいけない（リンクエラーになる）
- 方針: 2 種類ビルドする
  - A: kprobe モード（KPROBES=y, 追加パッチは path_umount のみ）… 公式推奨
  - B: manual モード（KPROBES=n, exec/open/read_write/stat にフック挿入）… フォールバック
