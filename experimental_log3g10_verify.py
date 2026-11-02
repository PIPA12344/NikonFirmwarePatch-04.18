"""Verify a prototype without trusting its output manifest."""
import argparse
import json
from pathlib import Path
from features import FEATURES
from z8log3g10.patcher import PROFILES
from z8log3g10.verify import verify_candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stock', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--features', nargs='+', choices=FEATURES, default=list(FEATURES))
    parser.add_argument('--gamut', choices=tuple(PROFILES), default='bt2020')
    parser.add_argument('--card-wav', action='store_true', help='Candidate includes the card WAV port')
    parser.add_argument('--card-wav-source', choices=('prebuilt', 'source'), default='prebuilt')
    parser.add_argument('--code-source', choices=('prebuilt', 'source'), default='prebuilt')
    parser.add_argument('--compiler', default='clang')
    parser.add_argument('--version', default='04.13')
    identity = parser.add_mutually_exclusive_group()
    identity.add_argument('--tag', default='e0')
    identity.add_argument('--no-tag', action='store_const', dest='tag', const='')
    args = parser.parse_args()
    print(json.dumps(verify_candidate(args.stock.read_bytes(), args.candidate.read_bytes(),
                                     args.features, args.version, args.tag, gamut=args.gamut, card_wav=args.card_wav,
                                     compiler=args.compiler, code_source=args.code_source,
                                     card_wav_source=args.card_wav_source), indent=2))


if __name__ == '__main__':
    main()
