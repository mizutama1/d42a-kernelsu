# d-42A 本家 KernelSU v0.9.5 ビルド詳細

対象: Lenovo d-42A / dtab Compact d-42A（ELF-8605L, trinket / SM6125, Android 12, kernel 4.14.190-perf, aarch64, 非GKI A-only）

このドキュメントは「何を素材に、どうやって `boot-ksu.img` を作ったか」の記録です。

---

## 1. 使った素材（4点セット）

| 素材 | 実体 / 入手元 | 用途 |
|---|---|---|
| 純正ファームウェア | `d-42A_S_S203037_2212092223_JP.zip`（2,287,941,964 B, lolinet）内の `boot.img`（64MB） | ramdisk / DTB / ロードアドレス / 純正 config の供給元。復旧用 `d42a/boot/stock_boot.img` としても保持 |
| 純正カーネルソース | Lenovo OSS tar `d_42a_d_42a_opensource_build_no_d_42a_s_s203037_2212092223_jp.tar`（830,024,222 B）内の `./kernel-4.14/msm-4.14` | ビルド対象。`VERSION=4 PATCHLEVEL=14 SUBLEVEL=190`、約71,700ファイル。同梱 `build_tools/`（clang 10.0.7 / aarch64-linux-android-4.9 / dtc / ufdt_apply_overlay）も使用 |
| 純正カーネル config | 上記 boot.img のカーネルに埋め込まれた IKCONFIG から抽出（`extract-ikconfig`）→ `d42a/config/d42a_defconfig`（160,393 B / 4,910 項目） | 純正と同一構成を出発点にする |
| KernelSU 本体 | `tiann/KernelSU` **v0.9.5**（4.14 非GKI 対応の最終リリース） | カーネル側のみ in-tree で組み込み（ksud は同梱 APK 側） |

補足:

- `dtbo.img` / `vbmeta` は変更していない。カーネルだけ差し替える構成のため、AVB（bootloader unlocked / `verifiedbootstate=orange`）はそのまま通る。
- 純正 boot.img のヘッダは **v2 / page size 4096**。AVB footer（`AVBf` @ 0x3FFFF00, vbmeta_offset 0xF60000）は再構築後のイメージには含まれない（unlocked のため不要）。

---

## 2. リポジトリ内ファイルの役割

```
d42a/
├── boot/stock_boot.img           純正 boot.img（復旧用＋再構築の土台）
├── config/d42a_defconfig         純正 .config を defconfig 化したもの
├── patches/apply_ksu_hooks.py    manual hook + path_umount backport を挿入
├── tools/bootimg.py              boot image v0/v1/v2 の unpack / repack
└── build.sh                      ソース検出 → KSU 組込 → パッチ → config → make → repack
.github/workflows/build-kernel.yml  GitHub Actions（ubuntu-22.04 / 手動実行 / A・B 2種）
```

---

## 3. ビルド手順の実体

### ① ソース展開（CI）

Release アセットの tar から**カーネル部分だけ**を展開する（830MB 全体を持ち込まない）。

```bash
tar -xf d42a-src.tar -C source ./kernel-4.14/msm-4.14
```

### ② カーネルディレクトリの同定

`find -name Makefile` は kbuild が生成した `out/obj/Makefile` を誤検出するため、
**`init/main.c` が存在し `VERSION = 4`** であることを条件にする。

### ③ KernelSU v0.9.5 の組み込み

公式 `kernel/setup.sh` を実行（`git clone` → `git checkout v0.9.5`）。やることは3つ。

- `KernelSU/kernel` → `drivers/kernelsu` のシンボリックリンク作成
- `drivers/Makefile` に `obj-$(CONFIG_KSU) += kernelsu/` を追記
- `drivers/Kconfig` に `source "drivers/kernelsu/Kconfig"` を追記

### ④ manual hook の挿入（`apply_ksu_hooks.py` / mode=manual）

4.14 では kprobe だけでは execve / faccessat / stat / read を確実に拾えないため、
公式ドキュメントの manual hook をこのツリーの実際の関数シグネチャに合わせて挿入する。

| ファイル | 挿入内容 |
|---|---|
| `fs/exec.c` | `do_execveat_common()` 冒頭で `ksu_handle_execveat()` / `ksu_handle_execveat_sucompat()` |
| `fs/open.c` | `SYSCALL_DEFINE3(faccessat)` 冒頭で `ksu_handle_faccessat()` |
| `fs/read_write.c` | `vfs_read()` 冒頭で `ksu_handle_vfs_read()`（`ksu_vfs_read_hook` 有効時のみ） |
| `fs/stat.c` | `SYSCALL_DEFINE4(newfstatat)` 冒頭で `ksu_handle_stat()` |
| `fs/namespace.c` | `path_umount()` / `can_umount()` のバックポート（5.9 未満に未存在） |
| `fs/internal.h` | `int path_umount(struct path *, int);` 宣言 |

スクリプトは「アンカーが丁度1箇所」「適用済みならスキップ」を検査し、異常時は非0で停止する。

### ⑤ カーネル config

純正 defconfig をコピーして `make d42a_defconfig` した後、`scripts/config` で**差分だけ**適用する。

```bash
scripts/config --file "$OUT/obj/.config" \
  -e MODULES -e OVERLAY_FS -e KALLSYMS -e KALLSYMS_ALL \
  -e KSU -d MODULE_SIG_FORCE \
  --set-str LOCALVERSION "-perf"
# manual モード: -d KPROBES -d KPROBE_EVENTS
# kprobe モード: -e KPROBES -e KPROBE_EVENTS
make O="$OUT/obj" ARCH=arm64 olddefconfig
```

純正 config からの最終差分は **3 項目のみ**（manual 版の実測）。

```
CONFIG_KSU=y                    (追加)
CONFIG_KSU_DEBUG                (未設定)
CONFIG_MODULE_SIG_FORCE=y → n
```

### ⑥ コンパイル

純正 `build_tools` の clang 10 を使用。`scripts/gcc-wrapper.py`（python2 製・警告即エラー）を
回避するため `CC` を直接 clang に向ける。

```bash
make -j$(nproc) ARCH=arm64 O=$OUT/obj \
  CC=$KD/build_tools/bin/clang \
  CROSS_COMPILE=aarch64-linux-android- \
  CLANG_TRIPLE=aarch64-linux-gnu- \
  DTC_EXT=$KD/build_tools/dtc \
  DTC_OVERLAY_TEST_EXT=$KD/build_tools/ufdt_apply_overlay \
  CONFIG_BUILD_ARM64_DT_OVERLAY=y KCFLAGS="-Wno-error" Image
```

得られた `Image` を `gzip -9` して `Image.gz` にする（純正と同じ gzip 圧縮方式）。

### ⑦ boot.img の再構築（`bootimg.py`）

純正 boot.img を unpack し、**kernel だけ差し替えて** repack する。

```bash
python3 d42a/tools/bootimg.py unpack d42a/boot/stock_boot.img out/boot_unpack
python3 d42a/tools/bootimg.py repack out/boot_unpack out/boot-ksu.img --kernel out/Image.gz
```

| 項目 | 純正 | ビルド後（manual） |
|---|---|---|
| header / page size | v2 / 4096 | 同じ |
| kernel | 14,887,248 B | 14,888,328 B |
| ramdisk | 709,145 B | 709,145 B（バイト一致） |
| dtb | 515,277 B（9 DTBs） | 515,277 B（バイト一致） |
| kernel_addr / ramdisk_addr | 0x8000 / 0x1000000 | 同じ |
| 出力サイズ | 67,108,864 B（AVB footer 含む） | 16,121,856 B（AVB なし） |

---

## 4. 設計判断

1. **v0.9.5 を採用**: 本家 KernelSU は GKI 前提へ移行済みで、4.14 は v0.9.5 が最終対応。
2. **2 モードをビルド**: v0.9.5 は `CONFIG_KPROBES=y` のとき `ksu_execveat_hook` /
   `ksu_vfs_read_hook` を定義しない（`#ifndef CONFIG_KPROBES`）ため、manual hook と
   同時有効化するとリンクエラーになる。よってモードを分離した。
   - A: `CONFIG_KPROBES=y` + path_umount backport のみ（公式推奨）
   - B: `CONFIG_KPROBES=n` + exec/open/read_write/stat へ manual hook
3. **実機では B（manual）を採用**: A は `su -c "cmd arg"`（空白を含む1引数）が
   `/system/bin/sh: /system/bin/su: No such file or directory` で失敗した。B は全パターン成功。
4. **`MODULE_SIG_FORCE` を無効化**: 純正 `vendor/*.ko` は Lenovo の鍵で署名済み。
   再ビルド鍵で強制検証すると既存 `.ko` が全てロード不能になるため。
   `MODULE_SIG=y` / `MODVERSIONS=y` / `LOCALVERSION="-perf"` / `PREEMPT=y` は維持し
   vermagic を純正と一致させている。
5. **ramdisk / DTB 無変更**: fstab・SELinux・dtbo overlay 適用結果を純正と同一に保ち、
   起動互換性を確保するため。

---

## 5. 再現方法

### GitHub Actions（推奨・約30分）

Actions → `build-kernelsu-official` → Run workflow。
`source_url` の既定値が純正 tar の Release アセット。
1 回の実行で `boot-ksu-kprobe` と `boot-ksu-manual` の 2 成果物ができる。

CI の注意点: ubuntu-22.04 には `libtinfo5` が無い（clang 10 が要求）ため、
focal の deb を dpkg するフォールバックを workflow に含めている。

### ローカル

```bash
KSU_HOOK_MODE=manual OUT_DIR=out-manual bash d42a/build.sh
```

---

## 6. 成果物

- 検証済みイメージ
  - `work/ksu/manual/boot-ksu.img`（採用・実機 flash 済み）
  - `work/ksu/kprobe/boot-ksu.img`（参考）
- ビルドログ / 最終 config: `work/ksu/manual/{build.log,kernel.config,Image,Image.gz}`
- 公開 Release: https://github.com/mizutama1/d42a-kernelsu/releases/tag/ksu-v0.9.5-nongki

### 書き込み / 復旧

```bash
adb reboot bootloader
fastboot boot  boot-ksu-manual.img     # 非破壊テスト
fastboot flash boot boot-ksu-manual.img
# 復旧
fastboot flash boot d42a/boot/stock_boot.img
```
