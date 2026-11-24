"""
Scan all Python files and extract external dependencies.
"""
import ast
import os
import sys
from pathlib import Path

# Standard library modules (Python built-ins) - should not be in requirements.txt
STDLIB_MODULES = {
    'os', 're', 'sys', 'json', 'time', 'datetime', 'pathlib', 'collections',
    'functools', 'itertools', 'hashlib', 'hmac', 'secrets', 'uuid', 'logging',
    'shutil', 'io', 'typing', 'types', 'warnings', 'difflib', 'sqlite3',
    'calendar', 'pickle', 'asyncio', 'subprocess', 'threading', 'multiprocessing',
    'email', 'base64', 'binascii', 'struct', 'array', 'math', 'random',
    'string', 'tempfile', 'contextlib', 'operator', 'copy', 'weakref',
    'abc', 'enum', 'dataclasses', 'importlib', 'inspect', 'gc', 'traceback',
    'http', 'urllib', 'socket', 'ssl', 'concurrent', 'queue', 'select',
}

# Project-local modules (your own .py files)
LOCAL_MODULES = {
    'app', 'database', 'doctor_database', 'drive_upload', 'sms',
    'interaction_analysis', 'check_exp', 'database_backup'
}

def extract_imports(file_path):
    """Extract import statements from a Python file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=str(file_path))
        
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # Get top-level module name
                    module = alias.name.split('.')[0]
                    imports.add(module)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    # Get top-level module name
                    module = node.module.split('.')[0]
                    imports.add(module)
        
        return imports
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return set()

def scan_project(root_dir):
    """Scan all Python files in the project."""
    all_imports = set()
    
    # Scan only main project files, not subdirectories with installed packages
    for py_file in Path(root_dir).glob('*.py'):
        if py_file.name.startswith('test_') or py_file.name in ['scan_dependencies.py', 'setup.py']:
            continue
        
        print(f"Scanning: {py_file.name}")
        imports = extract_imports(py_file)
        all_imports.update(imports)
    
    # Filter out standard library and local modules
    external_deps = all_imports - STDLIB_MODULES - LOCAL_MODULES
    
    return sorted(external_deps)

# Package name mappings (import name -> PyPI package name)
PACKAGE_MAPPINGS = {
    'cv2': 'opencv-python',
    'PIL': 'Pillow',
    'sklearn': 'scikit-learn',
    'yaml': 'PyYAML',
    'bs4': 'beautifulsoup4',
    'google': 'google-api-python-client',  # Note: multiple google packages exist
    'werkzeug': 'Werkzeug',
    'flask': 'Flask',
    'dotenv': 'python-dotenv',
    'qrcode': 'qrcode',
    'fpdf': 'fpdf',
}

if __name__ == '__main__':
    project_root = Path(__file__).parent
    print(f"\nScanning project: {project_root}\n")
    print("=" * 70)
    
    dependencies = scan_project(project_root)
    
    print(f"\n{'=' * 70}")
    print("EXTERNAL DEPENDENCIES FOUND:")
    print("=" * 70)
    
    for dep in dependencies:
        package_name = PACKAGE_MAPPINGS.get(dep, dep)
        print(f"  - {dep:20} -> {package_name}")
    
    print(f"\n{'=' * 70}")
    print("SUGGESTED requirements.txt entries:")
    print("=" * 70)
    
    for dep in dependencies:
        package_name = PACKAGE_MAPPINGS.get(dep, dep)
        print(package_name)
    
    print(f"\n{'=' * 70}")
