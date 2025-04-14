import os
import subprocess
import sys
from setuptools import setup

# Create the static directory if it doesn't exist
os.makedirs('src/talkpipe/app/static', exist_ok=True)

# Run the documentation generator
try:
    subprocess.run([
        sys.executable, 
        'src/talkpipe/app/unit_documentation_analyzer.py',
        'src',
        'src/talkpipe/app/static/unit-docs.html',
        'src/talkpipe/app/static/unit-docs.txt'
    ], check=True)
    print("Documentation generated successfully")
except Exception as e:
    print(f"Warning: Documentation generation failed: {e}")
    # Create empty files to prevent packaging errors
    for filename in ['src/talkpipe/app/static/unit-docs.html', 'src/talkpipe/app/static/unit-docs.txt']:
        with open(filename, 'w') as f:
            f.write(f"Documentation generation failed: {e}")

# Let setuptools_scm handle the rest
setup()