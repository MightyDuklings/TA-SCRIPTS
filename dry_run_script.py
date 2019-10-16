#! /usr/bin/env python
from __future__ import unicode_literals
from django.db import transaction

def main():
    pass

if __name__ == '__main__':
    import argparse
    from django import setup
    setup()
    parser = argparse.ArgumentParser(
        description=''
    )
    parser.add_argument(
        '--commit', dest='COMMIT', default=False, action='store_true',
        help='Commit script changes to DB'
    )
    args = parser.parse_args()
    with transaction.atomic():
        main()
        if not args.COMMIT:
            raise ValueError("Dry Run. Changes not committed")