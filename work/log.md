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

## 2026-11-23 05:40 両バリアントのビルド成功・検証
- 修正: config パス（out → $OUT/obj）、OUT_DIR の絶対パス化、kernel dir 自動検出が
  kbuild 生成の obj/Makefile を拾う問題（init/main.c 存在チェックで解決）
- run 45065888204 で A(kprobe)/B(manual) とも success、artifact 取得
- 両方 ramdisk/DTB 純正一致、config 差分は想定どおり
- 端末未接続のため実機テストは保留

## 2026-11-23 17:40 実機検証（root 成功・variant B 採用）
- A(kprobe): `su -c "echo hi"` が ENOENT、`su -c id` は成功 → kprobe sucompat の引数依存不具合
- B(manual): `su -c id` / `su -c 'id -u'` / `su -c 'pm list packages | wc -l'` すべて成功
- `fastboot flash boot work/ksu/manual/boot-ksu.img` → 再起動後も root 維持
- ksud module install: 初回 ENOENT は `adb push` の Git Bash パス変換が原因（`MSYS_NO_PATHCONV=1` で解決）
- Zygisk Next 1.5.3 + Zygisk Assistant 2.1.4 導入、zn-nsdaemon 起動確認
