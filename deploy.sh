set -x
set -e
rm -R dist/
python -m build
python -m twine upload --repository pypi dist/*

