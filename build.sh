echo "Prepare to clone conda and conda-build for metadata reading..."
mkdir conda_tmp
git clone https://github.com/conda/conda-build conda_tmp/conda-build
git clone https://github.com/conda/conda conda_tmp/conda
set PYTHONPATH=$PYTHONPATH:./conda_tmp/conda-build:./conda_tmp/conda
echo "PYTHONPATH below should include ./conda_tmp"
echo $PYTHONPATH
$PYTHON setup.py install --single-version-externally-managed --record=record.txt