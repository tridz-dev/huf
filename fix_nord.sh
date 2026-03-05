#!/bin/bash
echo "Cleaning NordVPN configuration and cache..."
rm -rf ~/Library/Application\ Support/com.nordvpn.macos
rm -rf ~/Library/Caches/com.nordvpn.macos
rm -rf ~/Library/Caches/com.crashlytics.data/com.nordvpn.macos
rm -rf ~/Library/Preferences/com.nordvpn.macos.plist
rm -rf ~/Library/Preferences/group.com.nordvpn.macos.firebase.plist
rm -rf ~/Library/Containers/com.nordvpn.macos*
echo "Cleanup complete. You can now launch NordVPN."
