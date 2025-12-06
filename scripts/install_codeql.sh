#!/bin/bash
set -e

INSTALL_DIR="tools/codeql_home"
CODEQL_VERSION="v2.23.2"
BUNDLE_URL="https://github.com/github/codeql-action/releases/download/codeql-bundle-${CODEQL_VERSION}/codeql-bundle-linux64.tar.gz"

mkdir -p "$INSTALL_DIR"

if [ -f "$INSTALL_DIR/codeql/codeql" ]; then
    echo "CodeQL already installed in $INSTALL_DIR/codeql"
    "$INSTALL_DIR/codeql/codeql" --version
    exit 0
fi

echo "Downloading CodeQL bundle ${CODEQL_VERSION}..."
wget -O codeql-bundle.tar.gz "$BUNDLE_URL"

echo "Extracting..."
tar -xzf codeql-bundle.tar.gz -C "$INSTALL_DIR"

rm codeql-bundle.tar.gz

echo "CodeQL installed successfully."
"$INSTALL_DIR/codeql/codeql" --version

echo "Please add the following to your PATH:"
echo "export PATH=\$PATH:$(pwd)/$INSTALL_DIR/codeql"
