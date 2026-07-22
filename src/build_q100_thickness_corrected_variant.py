#!/usr/bin/env python3
"""Compatibility entry point for the Q100 thickness-audit case."""
from build_thickness_corrected_campaign import build_one


if __name__ == "__main__":
    print(build_one(100))
