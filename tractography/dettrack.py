import argparse
import sys
import os

if __package__ is None or __package__ == "":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, script_dir)
    sys.path.insert(1, os.path.dirname(script_dir))
    from tractography import deterministic_tractography
    from connectivity import connectivity_from_streamlines
else:
    from .tractography import deterministic_tractography
    from .connectivity import connectivity_from_streamlines


def main():
    parser = argparse.ArgumentParser(description="Run deterministic tractography and connectivity computation")
    parser.add_argument("dwi", help="Preprocessed DWI file")
    parser.add_argument("mask", help="Brain mask file")
    parser.add_argument("bval", help="b-values file")
    parser.add_argument("bvec", help="b-vectors file")
    parser.add_argument("atlas", help="Atlas file aligned to DWI space")
    parser.add_argument("out_dir", help="Output directory")
    args = parser.parse_args()

    streamlines, affine, _ = deterministic_tractography(
        args.dwi, args.mask, args.bval, args.bvec, args.out_dir
    )
    connectivity_from_streamlines(streamlines, args.atlas, affine, args.out_dir)


if __name__ == "__main__":
    main()
