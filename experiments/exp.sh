#!/bin/bash
size=$1
echo "../config${size}.ini"
sudo cp "../config${size}.ini" ../config.ini
sudo python3 -u cec.py setup | sudo tee -a "setup${size}.log"
sudo python3 -u cec.py experiment | sudo tee -a "exp${size}.log"
sudo mv leader.log "leader${size}.log"
sudo git add .
sudo git commit -m "Automatic-Update-Exp${size}"
sudo git push