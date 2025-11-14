#!/bin/bash

# remove conflicting packages
sudo apt remove --purge ucx libucx-dev
sudo apt autoremove

# clean up residual files
sudo find /usr -name "*ucx*" -type f -delete 2>/dev/null

sudo apt update
sudo apt install -y libtool automake autoconf libltdl-dev pkg-config
sudo apt install -y make gcc g++ curl wget
sudo apt install -y build-essential

git clone https://github.com/openucx/ucx.git
cd ucx
./autogen.sh

make distclean 2>/dev/null || true
git clean -fdx
git reset --hard

./configure     \
         --prefix=/usr/local/new_ucx \
         --enable-shared             \
         --enable-mt                 \
         --enable-debug              \
         --enable-profiling          \
         --enable-frame-pointer      \
         --disable-static            \
         --disable-doxygen-doc       \
         --enable-optimizations      \
         --enable-cma                \
         --enable-devel-headers      \
         --with-cuda=/usr/local/new_cuda \
         --with-verbs                \
         --with-dm                   \
         --with-gdrcopy=/usr/local/new_gdrcopy   \
         --with-efa                  


make -j install-strip 
make -j$(nproc)
sudo make install

sudo ldconfig

export PATH=/usr/local/ucx/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/ucx/lib:$LD_LIBRARY_PATH

/usr/local/ucx/bin/ucx_info -v
/usr/local/ucx/bin/ucx_info -d | grep cuda || echo "no cuda support"