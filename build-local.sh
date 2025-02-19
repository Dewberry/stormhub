rm -rf dist
pip uninstall -y stormhub

# Ensure the build module is installed
pip install build

python -m build

# Get the name of the newly created wheel file in the dist directory
WHEEL_FILE=$(ls dist/*.whl 2>/dev/null)

if [ -z "$WHEEL_FILE" ]; then
    echo "No wheel file found in the dist directory."
    exit 1
fi

pip install "$WHEEL_FILE"

cd docs
./make.sh