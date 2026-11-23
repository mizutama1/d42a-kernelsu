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
```

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
