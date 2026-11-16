#!/usr/bin/env python3
"""Prepare only the private snapshot directory. Never inspect saved snapshots."""
import os
from pathlib import Path
import stat
import sys


FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def check_parent(fd, path):
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise RuntimeError(f'parent must be user-owned and not group/other-writable: {path}')


def prepare():
    raw_home = os.environ.get('HOME', '')
    home = Path(raw_home)
    if not raw_home or not home.is_absolute() or home.resolve() != home:
        raise RuntimeError('HOME must be an absolute canonical path without symlink components')
    parent_fd = os.open(home, FLAGS)
    try:
        check_parent(parent_fd, home)
        parent = home
        for name in ('.local', 'state', 'tmux-resurrect'):
            path = parent / name
            try:
                os.mkdir(name, mode=0o700, dir_fd=parent_fd)
            except FileExistsError:
                pass
            # Relative, no-follow opens bind validation and chmod to the same
            # directory inode. Never follow a symlink or enumerate the leaf.
            child_fd = os.open(name, FLAGS, dir_fd=parent_fd)
            try:
                info = os.fstat(child_fd)
                if name == 'tmux-resurrect':
                    if info.st_uid != os.getuid():
                        raise RuntimeError(f'snapshot directory is not owned by this user: {path}')
                    if stat.S_IMODE(info.st_mode) != 0o700:
                        os.fchmod(child_fd, 0o700)
                    if stat.S_IMODE(os.fstat(child_fd).st_mode) != 0o700:
                        raise RuntimeError(f'snapshot directory is not private: {path}')
                else:
                    check_parent(child_fd, path)
                os.fsync(child_fd)
                os.fsync(parent_fd)
            except BaseException:
                os.close(child_fd)
                raise
            os.close(parent_fd)
            parent_fd = child_fd
            parent = path
    finally:
        os.close(parent_fd)


if __name__ == '__main__':
    try:
        if len(sys.argv) != 1:
            raise RuntimeError('usage: prepare-persistence-state.py')
        prepare()
    except (OSError, RuntimeError) as error:
        print(f'tmux persistence state: {error}', file=sys.stderr)
        sys.exit(1)
