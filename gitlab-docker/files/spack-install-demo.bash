
mkdir -p /builds/root
git clone git://github.com/opadron/spack.git /builds/root/spack-build
cd /builds/root/spack-build
git checkout ecp-testing
source share/spack/setup-env.sh
spack spec readline
spack install patchelf
spack clean -a

echo
echo
echo
echo '=============================================='
echo 'Compiling readline from source'
echo '=============================================='
echo
echo
echo
sleep 10

time spack install readline
sleep 10

spack uninstall --all -y
spack mirror add mirror /mirror
base64 -d /volumes/package-signing-key > key
spack gpg trust key
rm key

echo
echo
echo
echo '=============================================='
echo 'Installing readline from binary mirror'
echo '=============================================='
echo
echo
echo
sleep 10

time spack install readline
sleep 10

