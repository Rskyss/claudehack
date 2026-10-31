#!/bin/bash
# Put the domain PAC back if 心安 switches the system proxy to its own port.
export PATH="/usr/bin:/bin:/usr/sbin:/sbin"
URL="http://127.0.0.1:8899/proxy.pac?v=8"
while true; do
  info=$(scutil --proxy 2>/dev/null || true)
  if ! printf '%s\n' "$info" | grep -q "ProxyAutoConfigURLString : ${URL}"; then
    /Library/PrivilegedHelperTools/local.claude-residential/install-proxy
  elif printf '%s\n' "$info" | grep -q "HTTPEnable : 1"; then
    /Library/PrivilegedHelperTools/local.claude-residential/install-proxy
  elif printf '%s\n' "$info" | grep -q "HTTPSEnable : 1"; then
    /Library/PrivilegedHelperTools/local.claude-residential/install-proxy
  fi
  sleep 15
done
