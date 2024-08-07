#!/usr/bin/env bash

brew unpack --patch curl
pushd curl-*
	./configure --enable-debug --with-openssl
	make
	find . -iname '*.dylib' | grep -v ".dSYM" | xargs -n 1 dsymutil
popd
# Import these and run the script to extract the type information
find . -iname '*.dylib' | grep -v ".dSYM" | xargs -n 1 -P 1 binaryninja-datatypes
find . -iname '*.bntl' -exec cp {} ../../bntls \;