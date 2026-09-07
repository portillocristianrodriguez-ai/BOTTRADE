"""Run the PAPER worker only after its persistent data has been restored."""
from pathlib import Path
import os
import sys
import time


def data_ready(directory):
    directory = Path(directory)
    return directory.is_dir() and (directory / '.bottrade-restored').is_file()


def main():
    directory = Path(os.environ.get('BOTTRADE_DATA_DIR', '/data')).resolve()
    if os.environ.get('ALPACA_PAPER', 'true').strip().lower() not in {'true', '1', 'yes', 'si', 'sí', 'on'}:
        raise RuntimeError('Persistent migration entrypoint requires PAPER')
    while not data_ready(directory):
        print(f'Waiting for verified data restore in {directory}; worker has not started', flush=True)
        time.sleep(10)
    os.chdir(directory)
    worker = Path(__file__).resolve().with_name('worker_entrypoint.py')
    os.execv(sys.executable, [sys.executable, str(worker)])


if __name__ == '__main__':
    main()
