rm -rf build
sphinx-apidoc -o source ../../stormhub
sphinx-build -M html source build