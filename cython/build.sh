#!/bin/bash

$PYTHON setup.py install

if [ `uname` == Darwin ]
then
    cp $RECIPE_DIR/post-link.sh $PREFIX/bin/.cython-post-link.sh
fi
