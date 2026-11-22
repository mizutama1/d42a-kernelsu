#!/usr/bin/env bash
# d-42A (ELF-8605L) / trinket 4.14.190 本家 KernelSU (v0.9.5) ビルドスクリプト
#  - Lenovo 純正ソース（kernel-4.14/msm-4.14）を自動検出
#  - tiann/KernelSU v0.9.5 を in-tree で組み込み
#  - 4.14 非 GKI のため manual hook を挿入 + kprobe を有効化
#  - 純正 config / ramdisk / DTB を使って boot.img を再構築
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

KSU_TAG="${KSU_TAG:-v0.9.5}"
MODE="${KSU_HOOK_MODE:-kprobe}"     # kprobe | manual
OUT="${OUT_DIR:-$ROOT/out}"

log() { printf '\n=== %s ===\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- 1. source
KD="${KERNEL_DIR:-}"
if [ -n "$KD" ] && [ ! -f "$KD/Makefile" ]; then
  echo "WARN: KERNEL_DIR=$KD に Makefile がありません。自動検出します"
  KD=""
fi
if [ -z "$KD" ]; then
  while IFS= read -r mk; do
    d="$(dirname "$mk")"
    case "$d" in ./work|./work/*|./out|./out/*|./.git|./.git/*) continue ;; esac
    if [ -d "$d/arch/arm64" ] && grep -qE '^VERSION[[:space:]]*=[[:space:]]*4' "$mk"; then
      KD="$d"; break
    fi
  done < <(find . -maxdepth 6 -type f -name Makefile | sort)
fi
[ -n "$KD" ] || die "カーネルソースが見つかりません（Makefile + arch/arm64 が必要）"
KD="$(cd "$KD" && pwd)"
echo "kernel dir : $KD"
grep -E '^(VERSION|PATCHLEVEL|SUBLEVEL) ' "$KD/Makefile" | tr '\n' ' '; echo

# ------------------------------------------------------- 2. KernelSU 本家
log "KernelSU $KSU_TAG (tiann/KernelSU) を組み込む"
cd "$KD"
if [ -d KernelSU ] || [ -e drivers/kernelsu ]; then
  echo "既に組み込み済み（スキップ）"
else
  curl -LSs "https://raw.githubusercontent.com/tiann/KernelSU/$KSU_TAG/kernel/setup.sh" -o /tmp/ksu-setup.sh
  sh /tmp/ksu-setup.sh "$KSU_TAG"
fi
[ -e drivers/kernelsu ] || die "drivers/kernelsu が作成されていません（setup.sh 失敗）"
grep -q 'kernelsu' drivers/Makefile || die "drivers/Makefile に kernelsu が追加されていません"

# ------------------------------------------------------- 3. manual hooks
log "フック設定をカーネルソースへ適用 (mode=$MODE)"
python3 "$ROOT/d42a/patches/apply_ksu_hooks.py" "$KD" "$MODE"

# ---------------------------------------------------------------- 4. config
log "defconfig を適用"
mkdir -p arch/arm64/configs
cp -f "$ROOT/d42a/config/d42a_defconfig" arch/arm64/configs/d42a_defconfig

export ARCH=arm64
export SUBARCH=arm
export LC_ALL=C

mkdir -p "$OUT/obj"
make O="$OUT/obj" ARCH=arm64 d42a_defconfig

# 純正 config からの変更点だけを明示する
#  - KSU: in-tree 組み込み（0.9.5 は OVERLAY_FS 必須）
#  - KPROBES: 0.9.5 の prctl/rename/input フックが kprobe を使う
#  - MODULE_SIG_FORCE: 純正 vendor .ko は Lenovo の鍵で署名済み。再ビルド鍵で
#    強制検証すると .ko が全滅するため無効化する
scripts/config --file out/.config \
  -e MODULES \
  -e OVERLAY_FS \
  -e KALLSYMS \
  -e KALLSYMS_ALL \
  -e KPROBES \
  -e KPROBE_EVENTS \
  -e KSU \
  -d MODULE_SIG_FORCE \
  --set-str LOCALVERSION "-perf"

for c in ${EXTRA_CONFIGS:-}; do
  echo "extra config: $c"
  scripts/config --file "$OUT/obj/.config" -e "$c"
done

make O="$OUT/obj" ARCH=arm64 olddefconfig

log "有効化チェック"
grep -E '^CONFIG_(KSU|MODULES|OVERLAY_FS|KPROBES|KPROBE_EVENTS|KALLSYMS_ALL|LOCALVERSION|MODVERSIONS|PREEMPT)=' "$OUT/obj/.config" || true
grep -E '^# CONFIG_MODULE_SIG_FORCE is not set' "$OUT/obj/.config" || true
grep -q '^CONFIG_KSU=y' "$OUT/obj/.config" || die "CONFIG_KSU が有効になっていません"
grep -q '^CONFIG_OVERLAY_FS=y' "$OUT/obj/.config" || die "CONFIG_OVERLAY_FS が有効になっていません"
if [ "$MODE" = "kprobe" ]; then
  grep -q '^CONFIG_KPROBES=y' "$OUT/obj/.config" || die "CONFIG_KPROBES が有効になっていません"
else
  grep -q '^# CONFIG_KPROBES is not set' "$OUT/obj/.config" || die "manual モードでは KPROBES を無効にしてください"
fi

# ----------------------------------------------------------------- 5. build
log "ビルド開始"
JOBS="$(nproc)"
if [ -x "$KD/build_tools/bin/clang" ]; then
  echo "toolchain: 純正 build_tools (clang 10 + aarch64-linux-android-4.9) を使用"
  # 純正 scripts/gcc-wrapper.py は python2 製かつ「警告 = 即エラー」なので
  # CC を直接 clang に向けてラッパーを回避する
  export PATH="$KD/build_tools/aarch64-linux-android-4.9/bin:$PATH"
  MAKEVARS=(
    ARCH=arm64 O="$OUT/obj"
    CC="$KD/build_tools/bin/clang"
    CROSS_COMPILE=aarch64-linux-android-
    DTC_EXT="$KD/build_tools/dtc"
    DTC_OVERLAY_TEST_EXT="$KD/build_tools/ufdt_apply_overlay"
    CONFIG_BUILD_ARM64_DT_OVERLAY=y
    CLANG_TRIPLE=aarch64-linux-gnu-
  )
else
  echo "toolchain: システムの clang / aarch64-linux-gnu- を使用"
  MAKEVARS=(
    ARCH=arm64 O="$OUT/obj"
    CC=clang
    CROSS_COMPILE=aarch64-linux-gnu-
    CLANG_TRIPLE=aarch64-linux-gnu-
  )
fi

set +e
make -j"$JOBS" "${MAKEVARS[@]}" KCFLAGS="-Wno-error" Image 2>&1 | tee "$OUT/build.log"
rc=${PIPESTATUS[0]}
set -e
if [ "$rc" -ne 0 ] || [ ! -f "$OUT/obj/arch/arm64/boot/Image" ]; then
  echo "Image ビルド失敗 (rc=$rc)。ログ末尾:"
  tail -n 80 "$OUT/build.log"
  die "ビルド失敗"
fi

IMG="$OUT/obj/arch/arm64/boot/Image"
gzip -9 -c "$IMG" > "$OUT/Image.gz"
ls -l "$IMG" out/Image.gz

# ------------------------------------------------------------- 6. repack boot
log "boot.img を再構築（純正 ramdisk / DTB を維持）"
rm -rf "$OUT/boot_unpack"
mkdir -p "$OUT"
python3 "$ROOT/d42a/tools/bootimg.py" unpack "$ROOT/d42a/boot/stock_boot.img" "$OUT/boot_unpack"
python3 "$ROOT/d42a/tools/bootimg.py" repack "$OUT/boot_unpack" "$OUT/boot-ksu.img" --kernel "$OUT/Image.gz"

cp -f "$IMG" "$OUT/Image"
cp -f "$OUT/obj/.config" "$OUT/kernel.config"
ls -l "$OUT"
echo "DONE: $OUT/boot-ksu.img"
