"""Create and replay one small decision using an installed package.

Copy this file outside the source checkout. Run with that package's Python:
    python replay_saved_decision.py unused-saved-decision.json
"""
import argparse
import json
from pathlib import Path

from bj.record import decision_json
from bj.replay import EXIT_STATUSES, replay_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path, help='new UTF-8 record filename, created exclusively')
    args = parser.parse_args()
    text = decision_json('T,4', 'T', shoe=(0, 1, 1, 0, 0, 0, 1, 1, 1, 1))
    with args.path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text + '\n')
    result = replay_file(args.path)
    print(json.dumps(result, indent=2, allow_nan=False))
    return EXIT_STATUSES[result['status']]


if __name__ == '__main__':
    raise SystemExit(main())
