#!/usr/bin/env python
"""
Master script that generates ALL output samples.

Delegates to setup_and_run.py in the sample_project directory.
Run from the examples/ directory:
    python scripts/generate_all_outputs.py
"""

import os
import subprocess
import sys

def main():
    """Run the sample project setup script to generate all outputs."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sample_project = os.path.join(script_dir, "..", "sample_project")
    setup_script = os.path.join(sample_project, "setup_and_run.py")

    if not os.path.exists(setup_script):
        print(f"ERROR: {setup_script} not found")
        sys.exit(1)

    print("Running sample project setup and output generation...")
    print(f"Script: {setup_script}")
    print("")

    result = subprocess.run(
        [sys.executable, setup_script],
        cwd=sample_project,
    )

    if result.returncode == 0:
        outputs_dir = os.path.join(script_dir, "..", "outputs")
        print(f"\nAll outputs saved to: {os.path.abspath(outputs_dir)}")
    else:
        print(f"\nScript failed with exit code {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
