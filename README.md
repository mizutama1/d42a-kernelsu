# d-42A (ELF-8605L) 本家 KernelSU v0.9.5 ビルド

Lenovo d-42A (dtab Compact / trinket / SM6125 / Android 12 / kernel 4.14.190) に
**本家 KernelSU (tiann/KernelSU) v0.9.5** を入れるためのカーネルビルド。

- 4.14 は非 GKI のため v0.9.5 が最終対応版
- kprobe を有効化 + manual hook（execve/faccessat/stat/read）を挿入
- `path_umount` をバックポートしてモジュール umount を有効化
- 純正 boot.img の ramdisk/DTB を維持し kernel のみ差し替え

## 構成
```
.github/workflows/build-kernel.yml  … GitHub Actions（手動実行）
d42a/build.sh                       … 組込み + ビルド + boot.img 再構築
d42a/patches/apply_ksu_hooks.py     … manual hook / path_umount 挿入
d42a/config/d42a_defconfig          … 純正カーネル config（実機から抽出）
d42a/boot/stock_boot.img            … 純正 boot.img（復旧用）
d42a/tools/bootimg.py               … boot image v2 unpack/repack
d42a/BUILD.md                       … 素材・パッチ・ビルド手順の詳細
```

ビルドの詳細（使用ソース、挿入パッチ、config 差分、boot.img 再構築）は
[`d42a/BUILD.md`](d42a/BUILD.md) を参照。

## 実行
Actions → `build-kernelsu-official` → Run workflow
（`source_url` 既定 = 純正ソース tar の Release アセット）

1回の実行で 2 種類をビルドする:
- **boot-ksu-kprobe**: `CONFIG_KPROBES=y` + path_umount のみ（公式推奨。v0.9.5 は kprobe で
  execve/read/faccessat/stat/prctl/rename をフックする）
- **boot-ksu-manual**: `CONFIG_KPROBES=n` + exec/open/read_write/stat へ manual hook 挿入
  （kprobe が壊れている端末向けフォールバック）

### 実機検証結果（d-42A, 2026-11-23）
| variant | 起動 | root | `su -c id` | `su -c "cmd arg"` |
|---|---|---|---|---|
| kprobe | OK | OK | OK | **NG** (`/system/bin/su: No such file or directory`) |
| manual | OK | OK | OK | OK |

→ **この端末では `boot-ksu-manual` を採用**（kprobe 版は execve フックが引数によって
  path 解決を壊すため、複数語の `su -c` が失敗する）

## 書き込み
```
adb reboot bootloader
fastboot boot boot-ksu.img        # 非破壊テスト
fastboot flash boot boot-ksu.img  # 本適用
```
復旧: `fastboot flash boot d42a/boot/stock_boot.img`

## 注意
- 純正 config は `CONFIG_MODULE_SIG_FORCE=y`。再ビルド鍵では純正 vendor .ko を
  検証できないため、このビルドでは無効化している（MODULE_SIG 自体は維持）。
- `CONFIG_KPROBES` は純正で無効 → 有効化（vermagic には影響しない）。

## ダウンロード（実機検証済み）
Release **`ksu-v0.9.5-nongki`** に boot イメージ一式を添付:
https://github.com/mizutama1/d42a-kernelsu/releases/tag/ksu-v0.9.5-nongki

- `boot-ksu-manual.img` … 推奨（この端末で `su -c "cmd arg"` も動作）
- `boot-ksu-kprobe.img` … kprobe 版（参考）
- `stock_boot.img` … 復旧用
- `KernelSU_v0.9.5_11872-release.apk` … マネージャ

Zygisk Next 1.5.3 + Zygisk Assistant 2.1.4 を ksud で導入し、再起動後も
root / モジュール 2 件が有効であることを確認済み。
