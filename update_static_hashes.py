#!/usr/bin/env python3
"""
Update static asset version hashes in templates.
Run this after modifying static/style.css or static/app.js.
"""

import hashlib
import os
import re

STATIC_DIR = 'static'
TEMPLATE_DIR = 'templates'

# Files to hash and their patterns in templates
ASSETS = {
    'style.css': r'/static/style\.css\?v=[a-f0-9]+',
    'app.js': r'/static/app\.js\?v=[a-f0-9]+',
}

# Templates that include each asset
ASSET_TEMPLATES = {
    'style.css': ['index.html', 'block.html', 'play.html', 'results.html', 
                  'help.html', 'gate.html', 'closed.html', 'not_found.html',
                  'block_auth.html', 'block_expired.html'],
    'app.js': ['index.html', 'block.html'],
}


def get_file_hash(filepath):
    """Get first 8 chars of MD5 hash for a file."""
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()[:8].lower()


def update_templates():
    """Update version hashes in all templates."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    for asset, pattern in ASSETS.items():
        asset_path = os.path.join(script_dir, STATIC_DIR, asset)
        if not os.path.exists(asset_path):
            print(f"Warning: {asset_path} not found, skipping")
            continue
        
        new_hash = get_file_hash(asset_path)
        new_ref = f'/static/{asset}?v={new_hash}'
        regex = re.compile(pattern)
        
        templates = ASSET_TEMPLATES.get(asset, [])
        for template in templates:
            template_path = os.path.join(script_dir, TEMPLATE_DIR, template)
            
            # Also check admin subdirectory
            if not os.path.exists(template_path):
                template_path = os.path.join(script_dir, TEMPLATE_DIR, 'admin', template)
            
            if not os.path.exists(template_path):
                continue
            
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if regex.search(content):
                updated = regex.sub(new_ref, content)
                if updated != content:
                    with open(template_path, 'w', encoding='utf-8') as f:
                        f.write(updated)
                    print(f"Updated {template}: {asset} -> v={new_hash}")


if __name__ == '__main__':
    update_templates()
    print("Done!")
