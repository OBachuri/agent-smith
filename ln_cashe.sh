rm -fr ~/goinfre/uv
rm -fr ~/goinfre/huggingface
rm -fr .venv
rm -fr ~/goinfre/venv

mkdir	~/goinfre/uv
mkdir	~/goinfre/huggingface
mkdir	~/goinfre/venv

ln -s ~/goinfre/uv ~/.cache/uv
ln -s ~/goinfre/huggingface ~/.cache/huggingface
ln -s ~/goinfre/venv .venv

#  uv pip list