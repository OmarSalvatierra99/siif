#!/usr/bin/env python3
"""
Batch processor for SIIF Excel files
Processes all .xlsx files from a directory into the database
"""

import os
import sys
from pathlib import Path
from io import BytesIO

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from scripts.utils import process_files_to_database

def progress_callback(percent, message):
    """Simple progress reporter"""
    print(f"[{percent:3d}%] {message}")

def main():
    # Initialize Flask app with development config
    app = create_app('development')

    # Get example folder path
    example_dir = Path(__file__).parent / 'example'

    if not example_dir.exists():
        print(f"Error: Directory {example_dir} not found")
        return 1

    # Find all Excel files
    excel_files = list(example_dir.glob('*.xlsx')) + list(example_dir.glob('*.xls'))
    excel_files = [f for f in excel_files if not f.name.startswith('~')]  # Skip temp files

    if not excel_files:
        print(f"No Excel files found in {example_dir}")
        return 1

    print(f"\nFound {len(excel_files)} Excel files:")
    for i, file in enumerate(excel_files, 1):
        size_mb = file.stat().st_size / (1024 * 1024)
        print(f"  {i}. {file.name} ({size_mb:.2f} MB)")

    print(f"\nTotal size: {sum(f.stat().st_size for f in excel_files) / (1024 * 1024):.2f} MB")
    print("\nStarting batch processing...\n")

    # Prepare files as list of tuples (filename, BytesIO)
    file_list = []
    for file_path in excel_files:
        with open(file_path, 'rb') as f:
            file_obj = BytesIO(f.read())
            file_list.append((file_path.name, file_obj))

    # Process with app context
    with app.app_context():
        try:
            lote_id, total_registros = process_files_to_database(
                file_list=file_list,
                usuario='batch_processor',
                progress_callback=progress_callback
            )

            print(f"\n{'='*60}")
            print(f"SUCCESS!")
            print(f"Lote ID: {lote_id}")
            print(f"Total registros procesados: {total_registros:,}")
            print(f"{'='*60}\n")

            return 0

        except Exception as e:
            print(f"\n{'='*60}")
            print(f"ERROR: {str(e)}")
            print(f"{'='*60}\n")
            import traceback
            traceback.print_exc()
            return 1

if __name__ == '__main__':
    sys.exit(main())
