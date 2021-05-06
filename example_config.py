from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

global_config = {
    'venv_dir': BASE_DIR / 'venv',
    'work_dir': BASE_DIR / 'work_dir',

    'telegram': {
        'token': None,
        # 'webhook': {
        #     'host': None,
        #     'port': None,
        # }
    },
}
