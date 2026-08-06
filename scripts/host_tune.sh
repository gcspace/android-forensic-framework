#!/usr/bin/env bash
sudo ulimit -n 65535
echo "* soft nofile 65535" | sudo tee -a /etc/security/limits.conf
echo "* hard nofile 65535" | sudo tee -a /etc/security/limits.conf
sudo sysctl -w fs.file-max=655350
echo "Host tuned successfully."
