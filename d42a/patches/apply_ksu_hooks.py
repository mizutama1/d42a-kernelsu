#!/usr/bin/env python3
"""本家 KernelSU (tiann/KernelSU) v0.9.5 を 4.14 カーネルへ組み込むパッチ。

非 GKI (4.14) では kprobe だけでは execve/faccessat/stat/read を拾えないため、
公式ドキュメントの manual hook をこの Lenovo 4.14 ツリー向けに合わせて挿入する。
  - fs/exec.c        : do_execveat_common → ksu_handle_execveat / _sucompat
  - fs/open.c        : faccessat          → ksu_handle_faccessat
  - fs/read_write.c  : vfs_read           → ksu_handle_vfs_read
  - fs/stat.c        : newfstatat         → ksu_handle_stat
  - fs/namespace.c   : path_umount backport (KSU_UMOUNT)
  - fs/internal.h    : path_umount 宣言

使い方: python3 apply_ksu_hooks.py <kernel_dir>
"""
import os
import sys

PATCHES = [
    # ------------------------------------------------------------------ execve
    (
        "fs/exec.c",
        "ksu_handle_execveat",
        """static int do_execveat_common(int fd, struct filename *filename,
			      struct user_arg_ptr argv,
			      struct user_arg_ptr envp,
			      int flags)
{
	char *pathbuf = NULL;
	struct linux_binprm *bprm;
	struct file *file;
	struct files_struct *displaced;
	int retval;
""",
        """#ifdef CONFIG_KSU
extern bool ksu_execveat_hook __read_mostly;
extern int ksu_handle_execveat(int *fd, struct filename **filename_ptr,
			       void *argv, void *envp, int *flags);
extern int ksu_handle_execveat_sucompat(int *fd,
					struct filename **filename_ptr,
					void *argv, void *envp, int *flags);
#endif

static int do_execveat_common(int fd, struct filename *filename,
			      struct user_arg_ptr argv,
			      struct user_arg_ptr envp,
			      int flags)
{
	char *pathbuf = NULL;
	struct linux_binprm *bprm;
	struct file *file;
	struct files_struct *displaced;
	int retval;

#ifdef CONFIG_KSU
	if (unlikely(ksu_execveat_hook))
		ksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);
	else
		ksu_handle_execveat_sucompat(&fd, &filename, &argv, &envp, &flags);
#endif
""",
    ),
    # ---------------------------------------------------------------- faccessat
    (
        "fs/open.c",
        "ksu_handle_faccessat",
        """SYSCALL_DEFINE3(faccessat, int, dfd, const char __user *, filename, int, mode)
{
	const struct cred *old_cred;
	struct cred *override_cred;
	struct path path;
	struct inode *inode;
	struct vfsmount *mnt;
	int res;
	unsigned int lookup_flags = LOOKUP_FOLLOW;

	if (mode & ~S_IRWXO)	/* where's F_OK, X_OK, W_OK, R_OK? */""",
        """#ifdef CONFIG_KSU
extern int ksu_handle_faccessat(int *dfd, const char __user **filename_user,
				int *mode, int *flags);
#endif

SYSCALL_DEFINE3(faccessat, int, dfd, const char __user *, filename, int, mode)
{
	const struct cred *old_cred;
	struct cred *override_cred;
	struct path path;
	struct inode *inode;
	struct vfsmount *mnt;
	int res;
	unsigned int lookup_flags = LOOKUP_FOLLOW;

#ifdef CONFIG_KSU
	ksu_handle_faccessat(&dfd, &filename, &mode, NULL);
#endif

	if (mode & ~S_IRWXO)	/* where's F_OK, X_OK, W_OK, R_OK? */""",
    ),
    # ----------------------------------------------------------------- vfs_read
    (
        "fs/read_write.c",
        "ksu_handle_vfs_read",
        """ssize_t vfs_read(struct file *file, char __user *buf, size_t count, loff_t *pos)
{
	ssize_t ret;

	if (!(file->f_mode & FMODE_READ))""",
        """#ifdef CONFIG_KSU
extern bool ksu_vfs_read_hook __read_mostly;
extern int ksu_handle_vfs_read(struct file **file_ptr,
			       char __user **buf_ptr, size_t *count_ptr,
			       loff_t **pos_ptr);
#endif

ssize_t vfs_read(struct file *file, char __user *buf, size_t count, loff_t *pos)
{
	ssize_t ret;

#ifdef CONFIG_KSU
	if (unlikely(ksu_vfs_read_hook))
		ksu_handle_vfs_read(&file, &buf, &count, &pos);
#endif

	if (!(file->f_mode & FMODE_READ))""",
    ),
    # -------------------------------------------------------------------- stat
    (
        "fs/stat.c",
        "ksu_handle_stat",
        """#if !defined(__ARCH_WANT_STAT64) || defined(__ARCH_WANT_SYS_NEWFSTATAT)
SYSCALL_DEFINE4(newfstatat, int, dfd, const char __user *, filename,
		struct stat __user *, statbuf, int, flag)
{
	struct kstat stat;
	int error;

	error = vfs_fstatat(dfd, filename, &stat, flag);""",
        """#ifdef CONFIG_KSU
extern int ksu_handle_stat(int *dfd, const char __user **filename_user,
			   int *flags);
#endif

#if !defined(__ARCH_WANT_STAT64) || defined(__ARCH_WANT_SYS_NEWFSTATAT)
SYSCALL_DEFINE4(newfstatat, int, dfd, const char __user *, filename,
		struct stat __user *, statbuf, int, flag)
{
	struct kstat stat;
	int error;

#ifdef CONFIG_KSU
	ksu_handle_stat(&dfd, &filename, &flag);
#endif

	error = vfs_fstatat(dfd, filename, &stat, flag);""",
    ),
    # ------------------------------------------------- path_umount (KSU_UMOUNT)
    (
        "fs/namespace.c",
        "can_umount",
        """static bool is_mnt_ns_file(struct dentry *dentry)""",
        """/* KernelSU: path_umount backport for < 5.9 (KSU_UMOUNT) */
static int can_umount(const struct path *path, int flags)
{
	struct mount *mnt = real_mount(path->mnt);

	if (flags & ~(MNT_FORCE | MNT_DETACH | MNT_EXPIRE | UMOUNT_NOFOLLOW))
		return -EINVAL;
	if (!may_mount())
		return -EPERM;
	if (path->dentry != path->mnt->mnt_root)
		return -EINVAL;
	if (!check_mnt(mnt))
		return -EINVAL;
	if (mnt->mnt.mnt_flags & MNT_LOCKED)
		return -EINVAL;
	if (flags & MNT_FORCE && !capable(CAP_SYS_ADMIN))
		return -EPERM;
	return 0;
}

int path_umount(struct path *path, int flags)
{
	struct mount *mnt = real_mount(path->mnt);
	int ret;

	ret = can_umount(path, flags);
	if (!ret)
		ret = do_umount(mnt, flags);

	dput(path->dentry);
	mntput_no_expire(mnt);
	return ret;
}

static bool is_mnt_ns_file(struct dentry *dentry)""",
    ),
    (
        "fs/internal.h",
        "path_umount",
        """extern void __init mnt_init(void);""",
        """extern void __init mnt_init(void);
int path_umount(struct path *path, int flags);""",
    ),
]


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    kdir = sys.argv[1]
    if not os.path.isfile(os.path.join(kdir, "Makefile")):
        print(f"ERROR: {kdir}/Makefile がありません")
        return 2

    for rel, marker, old, new in PATCHES:
        path = os.path.join(kdir, rel)
        if not os.path.isfile(path):
            print(f"ERROR: {rel} が見つかりません")
            return 1
        with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
            src = f.read()
        if new in src:
            print(f"[skip] {rel}: 適用済み")
            continue
        if marker in src and old not in src:
            print(f"[skip] {rel}: '{marker}' が既に存在（手動確認）")
            continue
        cnt = src.count(old)
        if cnt != 1:
            print(f"ERROR: {rel}: アンカーが {cnt} 箇所（1 箇所である必要あり）")
            return 1
        with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
            f.write(src.replace(old, new, 1))
        print(f"[ok] {rel}")

    print("KernelSU hooks の挿入が完了しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
