#!/usr/bin/env python3

from __future__ import print_function
import sys
from typing import List, Optional

if sys.version_info.major != 3:
    print('ERROR: use Python 3')
    sys.exit(1)
import shutil
import shlex
from pathlib import Path
from importlib import import_module
from subprocess import check_call
import argparse

BASE_DIR = Path(__file__).resolve().parent


def recursive_config_checker(example_dict: dict, checked_dict: dict, path: Optional[List[str]] = None) -> bool:
    if path is None:
        path = []
    result = True
    for key, evalue in example_dict.items():
        current_path = '.'.join(path[:] + [key])
        value = checked_dict.get(key, None)
        if value is None:
            result = False
            print(f'ERROR: config key "{current_path}" either missing or None')
            continue
        if type(evalue) != type(value) and evalue is not None:
            result = False
            print(f'ERROR: config key "{current_path}" value type does not match with example_config')
            continue
        if isinstance(evalue, dict) and isinstance(value, dict):
            result = result and recursive_config_checker(evalue, value, path[:] + [key])
    return result


def get_config():
    example_cfg_module = import_module('example_config')
    try:
        cfg_module = import_module('config')
    except ModuleNotFoundError:
        shutil.copy(BASE_DIR / 'example_config.py', BASE_DIR / 'config.py')
        print(f'Config file created with default values at {BASE_DIR}. Restart me')
        sys.exit(0)
    config_dict_name = 'global_config'
    try:
        example_cfg = getattr(example_cfg_module, config_dict_name)  # type: dict
        cfg = getattr(cfg_module, config_dict_name)  # type: dict
        config_ok = recursive_config_checker(example_cfg, cfg)
        if config_ok:
            return cfg
    except AttributeError:
        print(f'ERROR: config files must have top-level dictionary named "{config_dict_name}"')
    return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--init', action='store_true', help='set up environment')
    parser.add_argument('--systemd', action='store_true', help='install unit file')
    parser.add_argument('--run', action='store_true', help='start')
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    cfg = get_config()
    if cfg is None:
        print('Config check failed. Refer to example_config.py and edit config.py')
        sys.exit(1)
    args = parser.parse_args()
    venv_dir = cfg['venv_dir']
    if not isinstance(venv_dir, Path):
        venv_dir = Path(venv_dir).resolve()
    work_dir = cfg['work_dir']
    if not isinstance(work_dir, Path):
        work_dir = Path(work_dir).resolve()
    work_dir.mkdir(0o755, parents=True, exist_ok=True)

    if args.init:
        if not venv_dir.exists():
            check_call([sys.executable, '-m', 'venv', venv_dir])
        check_call([venv_dir / 'bin' / 'python', '-m', 'pip', 'install', '-r', 'requirements.txt'], cwd=BASE_DIR)
    if args.systemd:
        import getpass
        import uuid
        import os
        with open(BASE_DIR / 'systemd' / 'template.service', 'r') as f:
            tmpl = f.read()
        unit = tmpl.format(**{
            'description': f'{BASE_DIR.name}',
            'user': f'{getpass.getuser()}',
            'work_dir': f'{BASE_DIR}',
            'exec_start': f"{shlex.join([str(venv_dir / 'bin' / 'python'), '-m', 'ydl_bot'])}",
        })
        source_name = str(BASE_DIR / str(uuid.uuid4()))
        dest_name = f'/etc/systemd/system/{BASE_DIR.name}.service'
        with open(source_name, 'w') as f:
            f.write(unit)
        try:
            check_call(['sudo', 'cp', source_name, dest_name])
            check_call(['sudo', 'systemctl', 'daemon-reload'])
            check_call(['sudo', 'systemctl', 'enable', '--now', BASE_DIR.name])
        finally:
            os.remove(source_name)
    if args.run:
        try:
            check_call([venv_dir / 'bin' / 'python', '-m', 'ydl_bot'], cwd=BASE_DIR)
        except KeyboardInterrupt:
            pass
