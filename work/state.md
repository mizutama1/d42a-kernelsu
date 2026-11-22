# 状態: d-42A 本家 KernelSU v0.9.5

## 目的
- d-42A (Lenovo ELF-8605L, trinket/SM6125, Android 12, kernel 4.14.190) を
  **本家 KernelSU (tiann/KernelSU) v0.9.5** で root 化する
- KernelSU-Next 版は別プロジェクト (d-42akarnelsu) でビルド済みだが、ユーザー要望により本家で作り直し

## 前提・素材
- 純正ソース: Lenovo OSS tar（カーネルは kernel-4.14/msm-4.14, 4.14.190, build_tools 同梱）
  Release アセット: https://github.com/mizutama1/d42a-kernel/releases/download/src-4.14.190/d42a-src.tar
- 純正 boot.img / 実機 .config は d42a/ 以下にコピー済み
- 端末: serial HA18JVX3, bootloader unlocked

## 実装方針
- KernelSU v0.9.5 (非 GKI 最終版)
- Kconfig: CONFIG_KSU=y, CONFIG_KPROBES=y, CONFIG_KPROBE_EVENTS=y, CONFIG_OVERLAY_FS=y
- manual hook: fs/exec.c, fs/open.c, fs/read_write.c, fs/stat.c
- path_umount backport: fs/namespace.c + fs/internal.h (KSU_UMOUNT)
- CONFIG_MODULE_SIG_FORCE は無効化（純正 vendor .ko を読むため）
- toolchain は純正 build_tools (clang 10) を優先、gcc-wrapper.py は迂回

## 2026-11-23 05:40 ビルド完了（2 種）と検証
- Actions run `45065888204` = **success**（Build A / Build B 両方 + artifact アップ済み）
- A: `boot-ksu-kprobe`（公式推奨, CONFIG_KPROBES=y）
  - `work/ksu/kprobe/boot-ksu.img` 16,142,336 B, `Image` 35,109,376 B
  - config: KSU=y / KPROBES=y / KRETPROBES=y / KPROBE_EVENTS=y / OVERLAY_FS=y / MODULE_SIG_FORCE not set
- B: `boot-ksu-manual`（フォールバック, KPROBES off + manual hook）
  - `work/ksu/manual/boot-ksu.img` 16,121,856 B, `Image` 35,107,328 B
  - config: KSU=y / KPROBES not set / MODULE_SIG_FORCE not set
- 両方とも bootimg.py で unpack 検証済み:
  - **ramdisk / DTB は純正とバイト一致**（差分は kernel のみ）
  - `Linux version 4.14.190-perf ... clang 10.0.7 for Android NDK`
  - KernelSU version 11872（マネージャ APK v0.9.5_11872 と一致）
- マネージャ: `work/tools/KernelSU_v0.9.5_11872-release.apk`（8,527,498 B）
- 端末は USB 未接続（adb/fastboot どちらにも見えない）→ 実機テストは未実施
