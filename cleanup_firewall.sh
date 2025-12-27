#!/bin/bash
echo "Cleaning up nftables firewall rules..."
if sudo nft list table inet xctf > /dev/null 2>&1; then
    echo "Removing nftables table 'xctf'..."
    sudo nft delete table inet xctf
    echo "Table removed successfully"
else
    echo "No nftables table 'xctf' found"
fi
echo "Checking for orphaned components..."
sudo nft delete chain inet xctf sandbox_access 2>/dev/null && echo "Removed chain" || true
sudo nft delete map inet xctf sandbox_port_to_ip 2>/dev/null && echo "Removed map" || true
sudo nft delete set inet xctf static_ports 2>/dev/null && echo "Removed set" || true
sudo nft delete table inet xctf 2>/dev/null && echo "Removed table" || true
echo "Cleanup complete!"
