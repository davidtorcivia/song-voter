---
description: Update static asset version hashes after modifying CSS or JS files
---

# Update Static Asset Hashes

When you modify `static/style.css` or `static/app.js`, run the update script to bust browser caches:

// turbo
```bash
python update_static_hashes.py
```

This automatically updates all `?v=HASH` query strings in templates.

## Why?

Static assets are cached for 1 year (`max-age=31536000`). The version query string (`?v=hash`) ensures browsers fetch the new file when it changes.
