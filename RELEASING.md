# Releasing

## Before Releasing

1. Update the version in `pyproject.toml`.
2. Update `src/homely/__init__.py` `__version__`.
3. Add release notes to `CHANGELOG.md`.
4. Run:

```bash
python3 -m pip install -e ".[dev]"
python3 -m ruff check .
python3 -m pytest -q
python3 -m build
python3 -m twine check dist/*
```

## Publishing to PyPI

This repository includes a GitHub Actions publish workflow intended for Trusted Publishing.

Recommended flow:

1. Create a Git tag like `v0.1.0`.
2. Push the tag.
3. Create a GitHub release from that tag.
4. Let the publish workflow upload the built distributions to PyPI.

If you publish manually instead:

```bash
python3 -m build
python3 -m twine upload dist/*
```

## Notes

- Verify the `project.name` in `pyproject.toml` matches the final PyPI name you want.
- If you later rename the distribution but keep `import homely`, that is completely fine.
