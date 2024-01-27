dos2unix run.sh
sudo apt-get update
sudo apt-get install -y software-properties-common
sudo apt-add-repository -y ppa:swi-prolog/stable
sudo apt-get install -y swi-prolog
pip install -r requirements.txt
pip install git+https://github.com/yuce/pyswip@master#egg=pyswip
mkdir .tmp
sudo chmod -R 777 .tmp
mkdir .tmp/.placements
sudo chmod -R 777 .tmp/.placements
dos2unix fogArm.py
dos2unix fogWatcher.py
dos2unix test.py
dos2unix utils.py
sudo ln -s "$PWD/fogArm.py" /bin
sudo mv /bin/fogArmX.py /bin/fogarmx
sudo chmod ugo+x /bin/fogarmx
sudo ln -s "$PWD/fogArm.py" /bin
sudo mv /bin/fogArm.py /bin/fax
sudo chmod ugo+x /bin/fax
#python3 test.py

